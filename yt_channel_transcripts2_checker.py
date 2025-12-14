#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yt_channel_transcripts.py — Extrae transcripts de YouTube.

COMPATIBILIDAD:
- Alineado con youtube-transcript-api v1.2.3 (Latest).
- Usa el método .list() en lugar de .list_transcripts() para instancias.
- Soporte nativo para Proxies (Webshare) usando la API oficial.

CARACTERÍSTICAS:
- Anti-Ban (Freno de emergencia).
- Salida .txt con Timestamps [HH:MM:SS].
- Merge automático.
"""
import argparse
import csv
import json
import sys
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Variable global para detener ejecución si hay ban
STOP_EVENT = threading.Event()

def _ensure_deps():
    try:
        import yt_dlp  # noqa: F401
    except Exception as e:
        print("Error: falta yt-dlp. Instala con:\n  pip install yt-dlp\nDetalle:", e, file=sys.stderr)
        sys.exit(1)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: F401
    except Exception as e:
        print("Error: falta youtube-transcript-api. Instala con:\n  pip install youtube-transcript-api\nDetalle:", e, file=sys.stderr)
        sys.exit(1)

def slugify(text: str, maxlen: int = 100) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[^\w\-\.\(\) ]+', '', text, flags=re.UNICODE)
    text = text.replace(' ', '_')
    if len(text) > maxlen:
        text = text[:maxlen].rstrip('_-.')
    return text or "video"

def parse_date_yyyymmdd(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    try: return datetime.strptime(s, "%Y%m%d")
    except Exception: return None

def parse_date_iso(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    try: return datetime.strptime(s, "%Y-%m-%d")
    except Exception: return None

def is_short(entry: Dict[str, Any]) -> bool:
    url = entry.get("webpage_url") or entry.get("url") or ""
    if "/shorts/" in url: return True
    dur = entry.get("duration")
    try: return dur is not None and float(dur) < 61.0
    except Exception: return False

def _normalize_video_entry(e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    vid = e.get("id")
    url = e.get("webpage_url") or e.get("url")
    if not vid:
        if isinstance(url, str) and "watch?v=" in url:
            import urllib.parse as _u
            q = _u.parse_qs(_u.urlparse(url).query)
            vid = (q.get("v") or [None])[0]
    if not vid: return None

    title = e.get("title") or ""
    duration = e.get("duration")
    upload_date = e.get("upload_date")
    uploader = e.get("uploader") or e.get("channel")

    if isinstance(url, str):
        webpage_url = url if url.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
    else:
        webpage_url = f"https://www.youtube.com/watch?v={vid}"

    return {
        "id": vid, "title": title, "webpage_url": webpage_url,
        "duration": duration, "upload_date": upload_date, "uploader": uploader
    }

def _flatten_entries(obj: Any, out: List[Dict[str, Any]]):
    if isinstance(obj, list):
        for it in obj: _flatten_entries(it, out)
        return
    if not isinstance(obj, dict): return
    cand = _normalize_video_entry(obj)
    if cand: out.append(cand)
    ents = obj.get("entries")
    if isinstance(ents, list):
        for it in ents: _flatten_entries(it, out)

def _extract_with_tab_videos(ydl, url: str) -> List[Dict[str, Any]]:
    info = ydl.extract_info(url, download=False)
    out: List[Dict[str, Any]] = []
    _flatten_entries(info, out)
    return out

def _uploads_playlist_from_channel_id(channel_id: str) -> str:
    if channel_id and channel_id.startswith("UC"): return "UU" + channel_id[2:]
    return ""

def get_entries(channel_or_playlist_url: str, max_videos: Optional[int] = None) -> List[Dict[str, Any]]:
    import yt_dlp
    ydl_opts_tab = {
        "quiet": True, "extract_flat": True, "skip_download": True,
        "nocheckcertificate": True, "extractor_args": {"youtube": {"tab": ["videos"]}},
    }
    entries: List[Dict[str, Any]] = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts_tab) as ydl:
            entries = _extract_with_tab_videos(ydl, channel_or_playlist_url)
    except Exception: entries = []

    if len(entries) < 5:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True, "nocheckcertificate": True}) as ydl:
                info = ydl.extract_info(channel_or_playlist_url, download=False)
            extra = []
            _flatten_entries(info, extra)
            seen = {e["id"] for e in entries}
            for e in extra:
                if e["id"] not in seen:
                    entries.append(e)
                    seen.add(e["id"])
        except Exception: pass

    if len(entries) < 5:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(channel_or_playlist_url, download=False)
            ch_id = info.get("channel_id") or (info.get("id") if info.get("_type") == "channel" else None)
            upl = _uploads_playlist_from_channel_id(ch_id or "")
            if upl:
                upl_url = f"https://www.youtube.com/playlist?list={upl}"
                with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as ydl:
                    pinfo = ydl.extract_info(upl_url, download=False)
                upl_entries = []
                _flatten_entries(pinfo, upl_entries)
                seen = {e["id"] for e in entries}
                for e in upl_entries:
                    if e["id"] not in seen:
                        entries.append(e)
                        seen.add(e["id"])
        except Exception: pass

    if max_videos is not None and max_videos > 0: entries = entries[:max_videos]
    return entries

# ---------------------------------------------------------
# FORMATTING & WRITING
# ---------------------------------------------------------

def format_seconds(seconds: float) -> str:
    if seconds is None: seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def write_output(snippets, out_fmt: str, out_path: Path):
    out_fmt = out_fmt.lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    if out_fmt == 'json':
        data = [{"text": getattr(sn, "text", "") or sn.get('text'), 
                 "start": float(getattr(sn, "start", 0.0) or sn.get('start', 0.0)), 
                 "duration": float(getattr(sn, "duration", 0.0) or sn.get('duration', 0.0))} 
                for sn in snippets]
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    
    elif out_fmt == 'txt':
        lines = []
        for sn in snippets:
            # Compatibilidad con objeto (v1.2.3) y dict
            text = getattr(sn, "text", "") if hasattr(sn, "text") else sn.get('text', "")
            start = getattr(sn, "start", 0.0) if hasattr(sn, "start") else sn.get('start', 0.0)
            t_str = format_seconds(start)
            clean_text = text.replace('\n', ' ').replace('  ', ' ')
            lines.append(f"[{t_str}] {clean_text}")
        out_path.write_text("\n".join(lines), encoding='utf-8')
    
    else:
        try:
            from youtube_transcript_api.formatters import SRTFormatter, WebVTTFormatter
            formatter = SRTFormatter() if out_fmt == 'srt' else WebVTTFormatter()
            s = formatter.format_transcript(snippets)
            out_path.write_text(s, encoding='utf-8')
        except Exception:
            raise ValueError(f"Error formateando {out_fmt}")

def _extract_video_id_from_name(name_no_ext: str) -> Optional[str]:
    if len(name_no_ext) >= 11:
        candidate = name_no_ext[-11:]
        if re.match(r'^[A-Za-z0-9_-]{11}$', candidate): return candidate
    m = re.search(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", name_no_ext)
    if m: return m.group(1)
    return None

def scan_existing_ids(out_dir: Path, policy: str, target_fmt: str) -> set:
    exts = [target_fmt.lower()] if policy == "same-format" else ["txt", "json", "srt", "vtt"]
    ids = set()
    for ext in exts:
        for p in out_dir.rglob(f"*.{ext}"): 
            vid = _extract_video_id_from_name(p.stem)
            if vid: ids.add(vid)
    return ids

# ---------------------------------------------------------
# MERGE LOGIC
# ---------------------------------------------------------
def merge_outputs(out_dir: Path, out_fmt: str, channel_name: str):
    index_file = out_dir / "index.csv"
    if not index_file.exists():
        print("❌ No se encontró index.csv.")
        return

    print("\n🔄 Preparando unificación (Merge)...")
    rows = []
    with index_file.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    valid_rows = [r for r in rows if r['out_file'] and r['out_file'] != '-']
    if not valid_rows:
        print("⚠️ No hay archivos válidos.")
        return

    # Ordenar por fecha
    valid_rows.sort(key=lambda x: x.get('upload_date') or "00000000")

    merged_content = []
    count = 0

    print(f"   Ordenando {len(valid_rows)} transcripciones...")
    for row in valid_rows:
        fpath = Path(row['out_file'])
        if not fpath.is_absolute():
            fpath = out_dir / fpath.name
        
        if fpath.exists():
            try:
                content = fpath.read_text(encoding='utf-8')
                vid_date = row.get('upload_date', 'Unknown')
                if len(vid_date) == 8: vid_date = f"{vid_date[:4]}-{vid_date[4:6]}-{vid_date[6:]}"

                header = []
                header.append("=" * 60)
                header.append(f"VIDEO: {row['title']}")
                header.append(f"DATE:  {vid_date}")
                header.append(f"ID:    {row['video_id']}")
                header.append(f"LINK:  {row['url']}")
                header.append("=" * 60)
                
                merged_content.append("\n".join(header))
                merged_content.append(content)
                merged_content.append("\n\n")
                count += 1
            except Exception as e:
                print(f"   ⚠️ Error leyendo {fpath.name}: {e}")

    merge_filename = f"FULL_MERGE_{slugify(channel_name)}.txt"
    merge_path = out_dir / merge_filename
    merge_path.write_text("\n".join(merged_content), encoding='utf-8')

    print(f"✅ MERGE COMPLETADO: {count} videos.")
    print(f"📄 Archivo: {merge_path}")

# ---------------------------------------------------------
# FETCH LOGIC (FIXED FOR v1.2.3)
# ---------------------------------------------------------

def fetch_transcript_for_video(video: Dict[str, Any],
                               languages: List[str],
                               out_dir: Path,
                               out_fmt: str,
                               overwrite: bool,
                               translate_to: Optional[str],
                               proxy_config: Any) -> Dict[str, Any]:
    
    if STOP_EVENT.is_set():
        return {
            "video_id": video.get("id"), "title": video.get("title"), 
            "url": "", "out_file": None, "upload_date": video.get("upload_date"),
            "status": "aborted", "message": "Script detenido por bloqueo de IP"
        }

    from youtube_transcript_api import YouTubeTranscriptApi

    vid = video.get("id") or ""
    title = video.get("title") or ""
    url = video.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    udate = video.get("upload_date") or ""
    
    safe_title = slugify(title, 120)
    base = f"{safe_title}-{vid}"
    out_path = out_dir / f"{base}.{out_fmt.lower()}"

    res = {
        "video_id": vid, "title": title, "url": url, 
        "out_file": str(out_path), "upload_date": udate,
        "status": "", "message": ""
    }

    if out_path.exists() and not overwrite:
        res["status"] = "skipped"
        res["message"] = "ya existe"
        return res

    try:
        # CORRECCIÓN BASADA EN LA DOC v1.2.3
        # Siempre instanciamos la clase, con o sin proxy.
        if proxy_config:
            api = YouTubeTranscriptApi(proxy_config=proxy_config)
        else:
            api = YouTubeTranscriptApi() # Instanciación básica

        # Usamos el método .list() que pertenece al objeto, no .list_transcripts()
        transcript_list = api.list(vid)

        try:
            transcript = transcript_list.find_transcript(languages)
        except Exception:
            if translate_to:
                try:
                    first_tr = next(iter(transcript_list))
                    transcript = first_tr.translate(translate_to)
                except Exception as e_tr:
                    res.update({"out_file": None, "status": "no_transcript", "message": f"No traducible: {e_tr}"})
                    return res
            else:
                 res.update({"out_file": None, "status": "no_transcript", "message": f"Idiomas no encontrados: {languages}"})
                 return res

        # .fetch() devuelve un objeto FetchedTranscript que es iterable
        fetched = transcript.fetch()
        write_output(fetched, out_fmt, out_path)
        res["status"] = "ok"
        return res

    except AttributeError as ae:
        res.update({"out_file": None, "status": "error", "message": f"AttributeError (Posible versión mismatch): {ae}"})
        return res

    except Exception as e:
        error_str = str(e)
        # Gestión de bloqueo de IP
        if "blocking requests" in error_str or "Too Many Requests" in error_str:
            if not STOP_EVENT.is_set():
                STOP_EVENT.set()
                print("\n" + "="*60, file=sys.stderr)
                print("🛑 CRITICAL ERROR: YOUTUBE IP BLOCK DETECTED 🛑", file=sys.stderr)
                print("="*60, file=sys.stderr)
                print("Solución: Reinicia Router/VPN.", file=sys.stderr)
                print("="*60 + "\n", file=sys.stderr)
            res.update({"out_file": None, "status": "IP_BLOCKED", "message": "YouTube bloqueó la IP"})
            return res
        
        res.update({"out_file": None, "status": "no_transcript", "message": str(e)})
        return res

def main(argv=None):
    _ensure_deps()

    p = argparse.ArgumentParser()
    p.add_argument("channel_or_playlist_url")
    p.add_argument("-l", "--languages", nargs="+", default=["es", "en"])
    p.add_argument("-f", "--format", default="txt", choices=["txt", "json", "srt", "vtt"])
    p.add_argument("-o", "--outdir", default="channel_transcripts")
    p.add_argument("--max", type=int, default=None)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--since", type=str, default=None)
    p.add_argument("--until", type=str, default=None)
    p.add_argument("--include-shorts", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--translate-to", type=str, default=None)
    p.add_argument("--existing-policy", choices=["same-format", "any-format", "none"], default="same-format")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--proxy", type=str)
    p.add_argument("--webshare-user", type=str)
    p.add_argument("--webshare-pass", type=str)

    args = p.parse_args(argv)

    # Configuración de Proxy usando las clases de la doc
    proxy_conf = None
    if args.webshare_user and args.webshare_pass:
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            proxy_conf = WebshareProxyConfig(args.webshare_user, args.webshare_pass)
            print("🛡️ Usando Proxy Webshare", file=sys.stderr)
        except ImportError:
            print("Error: youtube_transcript_api no soporta Webshare.", file=sys.stderr)
            return 1
    elif args.proxy:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            proxy_conf = GenericProxyConfig(http_url=args.proxy, https_url=args.proxy)
            print(f"🛡️ Usando Proxy Genérico: {args.proxy}", file=sys.stderr)
        except ImportError:
            print("Error: youtube_transcript_api no soporta GenericProxyConfig.", file=sys.stderr)
            return 1

    base_out_dir = Path(args.outdir).resolve()
    print("📋 Listando vídeos…", file=sys.stderr)
    entries = get_entries(args.channel_or_playlist_url, max_videos=None)

    channel_name = "Unknown_Channel"
    if entries:
        first_valid = next((e for e in entries if e.get('uploader') or e.get('channel')), None)
        if first_valid:
            channel_name = first_valid.get('uploader') or first_valid.get('channel')
    
    out_dir = base_out_dir / slugify(channel_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.csv"
    
    print(f"📂 Carpeta: {out_dir}", file=sys.stderr)

    since_dt = parse_date_iso(args.since) if args.since else None
    until_dt = parse_date_iso(args.until) if args.until else None
    filtered = []
    for e in entries:
        if not e.get("id"): continue
        if not args.include_shorts and is_short(e): continue
        udt = parse_date_yyyymmdd(e.get("upload_date"))
        if since_dt and udt and udt < since_dt: continue
        if until_dt and udt and udt > until_dt: continue
        filtered.append(e)

    existing_ids = set()
    if args.existing_policy != "none" and not args.overwrite:
        existing_ids = scan_existing_ids(out_dir, args.existing_policy, args.format)

    to_process = [e for e in filtered if e.get("id") not in existing_ids]
    already = [e for e in filtered if e.get("id") in existing_ids]

    print(f"🚀 A procesar: {len(to_process)} (Existentes: {len(already)})", file=sys.stderr)

    if args.dry_run:
        print("-- DRY RUN --")
        return 0

    results = []
    if to_process:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futures = {
                ex.submit(
                    fetch_transcript_for_video,
                    video=e,
                    languages=args.languages,
                    out_dir=out_dir,
                    out_fmt=args.format,
                    overwrite=args.overwrite,
                    translate_to=args.translate_to,
                    proxy_config=proxy_conf
                ): e for e in to_process
            }
            
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                
                status = res.get("status")
                if status == "aborted": continue

                vid = res.get("video_id")
                title = res.get("title", "")[:50]
                ofile = Path(res.get("out_file")).name if res.get("out_file") else "-"
                
                msg_suffix = f" | {res.get('message')}" if status != "ok" else ""
                print(f"[{status}] {vid} | {title} -> {ofile}{msg_suffix}")
                
                if STOP_EVENT.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    break

    with index_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["video_id", "title", "url", "out_file", "status", "message", "upload_date"])
        writer.writeheader()
        for e in already:
            writer.writerow({
                "video_id": e.get("id"), "title": e.get("title"), "url": e.get("webpage_url"),
                "out_file": str(out_dir / f"{slugify(e.get('title') or '')}-{e.get('id')}.{args.format}"), 
                "status": "skipped-existing", "message": f"omito por politica",
                "upload_date": e.get("upload_date")
            })
        for r in results:
            writer.writerow(r)

    if STOP_EVENT.is_set():
        print("\n❌ DETENIDO POR BLOQUEO DE YOUTUBE.", file=sys.stderr)
    else:
        print("\n✅ Proceso finalizado correctamente.")

    if args.format in ['txt', 'srt', 'vtt']:
        try:
            print("\n" + "-"*40)
            q = input("¿Quieres crear un archivo UNIFICADO (Merge) de todos los transcripts? (y/N): ")
            if q.lower().strip() == 'y':
                merge_outputs(out_dir, args.format, channel_name)
        except KeyboardInterrupt:
            pass

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)