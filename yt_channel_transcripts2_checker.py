#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yt_channel_transcripts.py — Extrae transcripts de TODOS los vídeos de un canal o playlist de YouTube.

Corrección: listado robusto de videos
- Soporte de pestaña "Videos" del canal (extractor_args youtube:tab=videos)
- Aplanado RECURSIVO de estructuras con "entries" (shelves del canal)
- Fallback automático a la playlist "Uploads" (UU...) cuando sea posible

Novedad:
- **Comprobador de existentes**: tras listar, chequea si ya hay un archivo generado para cada vídeo
  y **omite** su procesamiento (idempotencia real). Controlable con --existing-policy.

Ejemplos:
  python yt_channel_transcripts.py https://www.youtube.com/@TedTalks -l es en -f txt -o out/
  python yt_channel_transcripts.py https://www.youtube.com/channel/UC4a-Gbdw7vOaccHmFo40b9g -f srt --since 2024-01-01
  python yt_channel_transcripts.py https://www.youtube.com/playlist?list=UU_x5XG1OV2P6uZZ5FSM9Ttw -f json --max 50

Requisitos:
  pip install yt-dlp youtube-transcript-api
"""
import argparse
import csv
import json
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

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


def slugify(text: str, maxlen: int = 80) -> str:
    text = re.sub(r'\\s+', ' ', text).strip()
    text = re.sub(r'[^\\w\\-\\.\\(\\) ]+', '', text, flags=re.UNICODE)
    text = text.replace(' ', '_')
    if len(text) > maxlen:
        text = text[:maxlen].rstrip('_-.')
    return text or "video"


def parse_date_yyyymmdd(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d")
    except Exception:
        return None


def parse_date_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def is_short(entry: Dict[str, Any]) -> bool:
    url = entry.get("webpage_url") or entry.get("url") or ""
    if "/shorts/" in url:
        return True
    dur = entry.get("duration")
    try:
        return dur is not None and float(dur) < 61.0
    except Exception:
        return False


def _normalize_video_entry(e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Devuelve un dict con campos normalizados si 'e' parece un vídeo."""
    vid = e.get("id")
    url = e.get("webpage_url") or e.get("url")
    if not vid:
        # Algunos items vienen como tipo 'url' con 'id' implícito en la URL
        if isinstance(url, str) and "watch?v=" in url:
            import urllib.parse as _u
            q = _u.parse_qs(_u.urlparse(url).query)
            vid = (q.get("v") or [None])[0]
    if not vid:
        return None

    title = e.get("title") or ""
    duration = e.get("duration")
    upload_date = e.get("upload_date")  # YYYYMMDD esperado

    # Normalizar URL completa:
    if isinstance(url, str):
        if url.startswith("http"):
            webpage_url = url
        else:
            webpage_url = f"https://www.youtube.com/watch?v={vid}"
    else:
        webpage_url = f"https://www.youtube.com/watch?v={vid}"

    return {
        "id": vid,
        "title": title,
        "webpage_url": webpage_url,
        "duration": duration,
        "upload_date": upload_date,
    }


def _flatten_entries(obj: Any, out: List[Dict[str, Any]]):
    """Aplana recursivamente cualquier estructura 'entries' buscando vídeos."""
    if isinstance(obj, list):
        for it in obj:
            _flatten_entries(it, out)
        return
    if not isinstance(obj, dict):
        return

    # Si tiene aspecto de vídeo, añádelo
    cand = _normalize_video_entry(obj)
    if cand:
        out.append(cand)

    # Si contiene más niveles (shelves, tabs, etc.), recorrer
    ents = obj.get("entries")
    if isinstance(ents, list):
        for it in ents:
            _flatten_entries(it, out)


def _extract_with_tab_videos(ydl, url: str) -> List[Dict[str, Any]]:
    """Usa la pestaña 'videos' del canal para listar TODO con continuations."""
    info = ydl.extract_info(url, download=False)
    out: List[Dict[str, Any]] = []
    _flatten_entries(info, out)
    return out


def _uploads_playlist_from_channel_id(channel_id: str) -> str:
    """Convierte UCxxxx -> UUxxxx (Uploads)."""
    if channel_id and channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return ""


def get_entries(channel_or_playlist_url: str, max_videos: Optional[int] = None) -> List[Dict[str, Any]]:
    import yt_dlp

    # 1) Intento principal: pestaña "videos" (maneja @handle, /channel/ID y /c/NAME)
    ydl_opts_tab = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "extractor_args": {"youtube": {"tab": ["videos"]}},  # fuerza pestaña videos
    }
    entries: List[Dict[str, Any]] = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts_tab) as ydl:
            entries = _extract_with_tab_videos(ydl, channel_or_playlist_url)
    except Exception:
        entries = []

    # 2) Si no conseguimos suficientes entradas, probar directamente lo que sea (playlist/canal),
    #    aplanando recursivamente cualquier estructura.
    if len(entries) < 5:  # umbral heurístico
        try:
            ydl_opts_any = {
                "quiet": True,
                "extract_flat": True,
                "skip_download": True,
                "nocheckcertificate": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts_any) as ydl:
                info = ydl.extract_info(channel_or_playlist_url, download=False)
            extra: List[Dict[str, Any]] = []
            _flatten_entries(info, extra)
            # mezclar evitando duplicados por id
            seen = {e["id"] for e in entries}
            for e in extra:
                if e["id"] not in seen:
                    entries.append(e)
                    seen.add(e["id"])
        except Exception:
            pass

    # 3) Fallback final: si parece un canal, construir playlist de 'Uploads' y extraerla
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
                upl_entries: List[Dict[str, Any]] = []
                _flatten_entries(pinfo, upl_entries)
                # mezclar
                seen = {e["id"] for e in entries}
                for e in upl_entries:
                    if e["id"] not in seen:
                        entries.append(e)
                        seen.add(e["id"])
        except Exception:
            pass

    # Recortar si se pidió
    if max_videos is not None and max_videos > 0:
        entries = entries[:max_videos]
    return entries


def fmt_srt(snippets):
    def srt_time(sec: float) -> str:
        from math import floor
        h = floor(sec / 3600)
        m = floor((sec % 3600) / 60)
        s = floor(sec % 60)
        ms = int(round((sec - floor(sec)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, sn in enumerate(snippets, 1):
        start = float(getattr(sn, 'start', 0.0))
        dur = float(getattr(sn, 'duration', 0.0))
        end = start + dur
        text = getattr(sn, 'text', '')
        lines.append(str(i))
        lines.append(f"{srt_time(start)} --> {srt_time(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def fmt_vtt(snippets):
    def vtt_time(sec: float) -> str:
        from math import floor
        h = floor(sec / 3600)
        m = floor((sec % 3600) / 60)
        s = sec - (h * 3600 + m * 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:06.3f}"
        return f"{m:02d}:{s:06.3f}"

    lines = ["WEBVTT", ""]
    for sn in snippets:
        start = float(getattr(sn, 'start', 0.0))
        dur = float(getattr(sn, 'duration', 0.0))
        end = start + dur
        text = getattr(sn, 'text', '')
        lines.append(f"{vtt_time(start)} --> {vtt_time(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_output(snippets, out_fmt: str, out_path: Path):
    out_fmt = out_fmt.lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_fmt == 'json':
        data = [{
            "text": getattr(sn, "text", ""),
            "start": float(getattr(sn, "start", 0.0)),
            "duration": float(getattr(sn, "duration", 0.0)),
        } for sn in snippets]
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return

    if out_fmt == 'txt':
        text = "\\n".join(getattr(sn, "text", "") for sn in snippets)
        out_path.write_text(text, encoding='utf-8')
        return

    if out_fmt == 'srt':
        try:
            from youtube_transcript_api.formatters import SRTFormatter
            s = SRTFormatter().format_transcript(snippets)
        except Exception:
            s = fmt_srt(snippets)
        out_path.write_text(s, encoding='utf-8')
        return

    if out_fmt == 'vtt':
        try:
            from youtube_transcript_api.formatters import WebVTTFormatter
            s = WebVTTFormatter().format_transcript(snippets)
        except Exception:
            s = fmt_vtt(snippets)
        out_path.write_text(s, encoding='utf-8')
        return

    raise ValueError(f"Formato no soportado: {out_fmt}. Usa txt|json|srt|vtt")


# ----------------------
# EXISTING FILES CHECKER
# ----------------------
def _is_date_token(tok: str) -> bool:
    # YYYY-MM-DD
    if len(tok) != 10:
        return False
    try:
        datetime.strptime(tok, "%Y-%m-%d")
        return True
    except Exception:
        return False


def _extract_video_id_from_name(name_no_ext: str) -> Optional[str]:
    """
    Intenta extraer el video_id de 11 chars del nombre de archivo.
    Nuestros nombres son: [YYYY-MM-DD_]VIDEOID_slug...
    """
    parts = name_no_ext.split("_", 2)
    if parts:
        idx = 1 if _is_date_token(parts[0]) and len(parts) > 1 else 0
        cand = parts[idx]
        if len(cand) == 11:
            return cand
    # Fallback más laxo: buscar una secuencia de 11 chars válidos
    m = re.search(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", name_no_ext)
    if m:
        return m.group(1)
    return None


def scan_existing_ids(out_dir: Path, policy: str, target_fmt: str) -> set:
    """
    Devuelve un set de video_ids que ya tienen archivo generado
    según la política indicada:
      - 'same-format': sólo si existe el mismo formato
      - 'any-format': si existe en cualquier formato (txt/json/srt/vtt)
    """
    exts = [target_fmt.lower()] if policy == "same-format" else ["txt", "json", "srt", "vtt"]
    ids = set()
    for ext in exts:
        for p in out_dir.glob(f"*.{ext}"):
            vid = _extract_video_id_from_name(p.stem)
            if vid:
                ids.add(vid)
    return ids


def fetch_transcript_for_video(video: Dict[str, Any],
                               languages: List[str],
                               out_dir: Path,
                               out_fmt: str,
                               overwrite: bool = False,
                               translate_to: Optional[str] = None) -> Dict[str, Any]:
    from youtube_transcript_api import YouTubeTranscriptApi

    vid = video.get("id") or ""
    title = video.get("title") or ""
    url = video.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    upload_date = video.get("upload_date") or ""
    duration = video.get("duration")

    date_prefix = ""
    dt = parse_date_yyyymmdd(upload_date)
    if dt:
        date_prefix = dt.strftime("%Y-%m-%d") + "_"
    base = f"{date_prefix}{vid}_{slugify(title, 60)}".strip("_")
    out_path = out_dir / f"{base}.{out_fmt.lower()}"
    if out_path.exists() and not overwrite:
        return {"video_id": vid, "title": title, "url": url, "out_file": str(out_path), "status": "skipped", "message": "ya existe"}

    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(vid, languages=languages)
    except Exception as e1:
        if translate_to:
            try:
                lst = api.list(vid)
                tr = None
                for cand in lst:
                    try:
                        tr = cand.translate(translate_to)
                        break
                    except Exception:
                        continue
                if tr is None:
                    return {"video_id": vid, "title": title, "url": url, "out_file": None, "status": "no_transcript", "message": f"no hay transcript o no se puede traducir: {e1}"}
                fetched = tr.fetch()
            except Exception as e2:
                return {"video_id": vid, "title": title, "url": url, "out_file": None, "status": "error", "message": f"{e1} | translate fallo: {e2}"}
        else:
            return {"video_id": vid, "title": title, "url": url, "out_file": None, "status": "no_transcript", "message": str(e1)}

    try:
        write_output(fetched, out_fmt, out_path)
        return {"video_id": vid, "title": title, "url": url, "out_file": str(out_path), "status": "ok", "message": ""}
    except Exception as ew:
        return {"video_id": vid, "title": title, "url": url, "out_file": None, "status": "write_error", "message": str(ew)}


def main(argv=None):
    _ensure_deps()

    p = argparse.ArgumentParser(description="Extrae transcripts de todos los vídeos de un canal/playlist de YouTube.")
    p.add_argument("channel_or_playlist_url", help="URL de canal (@handle, /channel/ID, /c/NAME), de 'Videos' del canal o de playlist (incluida la 'Uploads')")
    p.add_argument("-l", "--languages", nargs="+", default=["es", "en"], help="Preferencia de idiomas (por defecto: es en)")
    p.add_argument("-f", "--format", default="txt", choices=["txt", "json", "srt", "vtt"], help="Formato de salida (por defecto: txt)")
    p.add_argument("-o", "--outdir", default="channel_transcripts", help="Directorio de salida (por defecto: channel_transcripts)")
    p.add_argument("--max", type=int, default=None, help="Máximo de vídeos a procesar (por defecto: todos)")
    p.add_argument("--workers", type=int, default=8, help="Hilos de procesamiento concurrente (por defecto: 8)")
    p.add_argument("--since", type=str, default=None, help="Solo vídeos con fecha de subida >= YYYY-MM-DD")
    p.add_argument("--until", type=str, default=None, help="Solo vídeos con fecha de subida <= YYYY-MM-DD")
    p.add_argument("--include-shorts", action="store_true", help="Incluir YouTube Shorts (por defecto: se excluyen)")
    p.add_argument("--overwrite", action="store_true", help="Sobrescribir archivos ya existentes")
    p.add_argument("--translate-to", type=str, default=None, help="Si no hay transcript en tus idiomas, intenta traducir a este idioma (ej.: es)")
    # NUEVO: política para existentes y dry-run
    p.add_argument("--existing-policy", choices=["same-format", "any-format", "none"], default="same-format",
                   help="Cómo decidir si un vídeo ya está descargado: 'same-format' (por defecto), 'any-format' o 'none' (ignorar)")
    p.add_argument("--dry-run", action="store_true", help="No descarga nada; solo lista qué se procesaría/omitiría")

    args = p.parse_args(argv)

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.csv"

    print("📋 Listando vídeos del canal/playlist…", file=sys.stderr)
    entries = get_entries(args.channel_or_playlist_url, max_videos=None)

    # Filtros por shorts y fechas
    since_dt = parse_date_iso(args.since) if args.since else None
    until_dt = parse_date_iso(args.until) if args.until else None

    filtered = []
    for e in entries:
        if not e.get("id"):
            continue
        if not args.include_shorts and is_short(e):
            continue
        udt = parse_date_yyyymmdd(e.get("upload_date"))
        if since_dt and udt and udt < since_dt:
            continue
        if until_dt and udt and udt > until_dt:
            continue
        filtered.append(e)

    # NUEVO: escaneo de existentes en disco
    existing_ids = set()
    if args.existing_policy != "none" and not args.overwrite:
        existing_ids = scan_existing_ids(out_dir, args.existing_policy, args.format)
        if existing_ids:
            print(f"🔁 Detectados ya en disco ({args.existing_policy}): {len(existing_ids)} IDs.", file=sys.stderr)

    # Excluir los ya existentes
    to_process = [e for e in filtered if e.get("id") not in existing_ids]
    already = [e for e in filtered if e.get("id") in existing_ids]

    print(f"🔎 Vídeos totales tras filtros: {len(filtered)}", file=sys.stderr)
    print(f"⏭️  Omitidos por existir: {len(already)}", file=sys.stderr)
    print(f"🚀 A procesar ahora: {len(to_process)}", file=sys.stderr)

    if args.dry_run:
        # Listado rápido
        print("\n-- DRY RUN --")
        for e in already[:20]:
            print(f"[EXISTS] {e.get('id')} | {e.get('title','')[:70]}")
        if len(already) > 20:
            print(f"... y {len(already)-20} más ya existentes.")
        for e in to_process[:20]:
            print(f"[DO]     {e.get('id')} | {e.get('title','')[:70]}")
        if len(to_process) > 20:
            print(f"... y {len(to_process)-20} más por hacer.")
        return 0

    if len(to_process) == 0:
        print("Nada que hacer: todo ya existente según la política seleccionada.", file=sys.stderr)
        # Aun así escribimos un índice vacío para consistencia
        with index_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["video_id", "title", "url", "out_file", "status", "message"])
            writer.writeheader()
        return 0

    results = []
    from youtube_transcript_api import YouTubeTranscriptApi  # rápida validación de import
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futures = {
            ex.submit(
                fetch_transcript_for_video,
                video=e,
                languages=args.languages,
                out_dir=out_dir,
                out_fmt=args.format,
                overwrite=args.overwrite,
                translate_to=args.translate_to
            ): e for e in to_process
        }
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            status = res.get("status")
            vid = res.get("video_id")
            title = res.get("title", "")[:60]
            ofile = res.get("out_file") or "-"
            msg = res.get("message", "")
            print(f"[{status}] {vid} | {title} -> {ofile} {('('+msg+')') if msg else ''}")

    with index_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["video_id", "title", "url", "out_file", "status", "message"])
        writer.writeheader()
        # Añadimos también los ya existentes al índice como 'skipped-existing'
        for e in already:
            writer.writerow({
                "video_id": e.get("id"),
                "title": e.get("title"),
                "url": e.get("webpage_url"),
                "out_file": "",  # desconocido (podrían existir en otro formato)
                "status": "skipped-existing",
                "message": f"omito por política={args.existing_policy}",
            })
        for r in results:
            writer.writerow(r)

    oks = sum(1 for r in results if r["status"] == "ok")
    skipped = len(already) + sum(1 for r in results if r["status"] == "skipped")
    no_tr = sum(1 for r in results if r["status"] == "no_transcript")
    werr = sum(1 for r in results if r["status"] == "write_error")
    errs = sum(1 for r in results if r["status"] == "error")

    print("\nResumen:")
    print(f"  ✅ OK: {oks}")
    print(f"  ⏭️  Skipped (existente+ya-existente): {skipped}")
    print(f"  🙅 No transcript: {no_tr}")
    print(f"  📝 Write error: {werr}")
    print(f"  ⚠️ Otros errores: {errs}")
    print(f"📄 Índice CSV: {index_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\\nCancelado por el usuario.", file=sys.stderr)
        sys.exit(130)
