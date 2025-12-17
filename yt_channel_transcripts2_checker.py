#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yt_channel_transcripts.py — Gestor de Transcripts de YouTube.

VERSION 3.2:
- Verificación REAL de conexión a internet (Ping 8.8.8.8) tras reinicio de ONT.
- Tiempos de espera dinámicos (continúa en cuanto vuelve la línea).
"""
import argparse
import csv
import json
import sys
import re
import os
import threading
import time
import urllib.request
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any, Optional, Tuple

# Variable global para detener ejecución si hay ban
STOP_EVENT = threading.Event()
CONFIG_FILE = Path("config.json")
MERGE_SPLIT_SIZE = 1_000_000 

def _ensure_deps():
    try:
        import yt_dlp  # noqa: F401
    except Exception as e:
        print("Error: falta yt-dlp. Instala con:\n  pip install yt-dlp", file=sys.stderr)
        sys.exit(1)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: F401
    except Exception as e:
        print("Error: falta youtube-transcript-api. Instala con:\n  pip install youtube-transcript-api", file=sys.stderr)
        sys.exit(1)

# --- CONFIG MANAGER ---
def load_global_config() -> Dict:
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except: pass
    return {}

def save_global_config(new_data: Dict):
    current = load_global_config()
    current.update(new_data)
    try:
        CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding='utf-8')
        print(f"✅ Configuración guardada en {CONFIG_FILE}")
    except Exception as e:
        print(f"⚠️ Error guardando config: {e}")

# --- NETWORK UTILS ---
def check_internet(host="8.8.8.8", port=53, timeout=3):
    """
    Intenta conectar con Google DNS para verificar si hay salida a internet real.
    """
    try:
        socket.setdefaulttimeout(timeout)
        # Intentamos abrir un socket TCP al puerto DNS de Google
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        return True
    except Exception:
        return False

# --- HOME ASSISTANT TRIGGER ---
def trigger_ha_restart(config: Dict):
    url = config.get("ha_url")
    token = config.get("ha_token")
    script_entity = config.get("ha_script_id") 

    if not url or not token or not script_entity:
        print("⚠️ Faltan datos de Home Assistant en config.json.", file=sys.stderr)
        return False

    if url.endswith("/"): url = url[:-1]
    api_endpoint = f"{url}/api/services/script/turn_on"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps({"entity_id": script_entity}).encode("utf-8")

    print(f"\n🔄 [HA] Enviando orden de reinicio a {script_entity}...", file=sys.stderr)
    
    try:
        req = urllib.request.Request(api_endpoint, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req) as response:
            if response.status in [200, 201]:
                print("✅ [HA] Orden recibida. Esperando reinicio del router...", file=sys.stderr)
                
                # 1. Espera inicial fija (30s) para dar tiempo a que se apague
                print("⏳ Esperando 30s a que se corte la conexión...", end="", flush=True)
                time.sleep(30)
                print(" Hecho.")

                # 2. Bucle de comprobación (Ping)
                print("🔎 Buscando señal de internet (Ping Google)...", file=sys.stderr)
                max_retries = 60 # 60 intentos * 5s = 300s (5 min timeout)
                
                for i in range(max_retries):
                    if check_internet():
                        print(f"\n✅ ¡CONEXIÓN RESTABLECIDA! (Intento {i+1})")
                        time.sleep(2) # Un respiro extra para estabilidad
                        return True
                    
                    # Feedback visual
                    sys.stderr.write("." if i % 10 != 0 else f" {i*5}s ")
                    sys.stderr.flush()
                    time.sleep(5)
                
                print("\n❌ Timeout: Internet no volvió tras 5 minutos.", file=sys.stderr)
                return False
            else:
                print(f"❌ Error HA: Status {response.status}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Fallo conectando a Home Assistant: {e}", file=sys.stderr)
    
    return False

# --- UTILS ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

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

def format_seconds(seconds: float) -> str:
    if seconds is None: seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def is_short(entry: Dict[str, Any]) -> bool:
    url = entry.get("webpage_url") or entry.get("url") or ""
    if "/shorts/" in url: return True
    dur = entry.get("duration")
    try: return dur is not None and float(dur) < 61.0
    except Exception: return False

# --- METADATA MANAGER ---
def save_channel_meta(folder: Path, data: Dict):
    meta_file = folder / ".channel_meta.json"
    try:
        if meta_file.exists():
            try:
                existing = json.loads(meta_file.read_text(encoding='utf-8'))
                existing.update(data)
                data = existing
            except: pass
        meta_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"⚠️ No se pudo guardar metadatos en {folder}: {e}")

def load_channel_meta(folder: Path) -> Dict:
    meta_file = folder / ".channel_meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding='utf-8'))
        except: pass
    return {}

# --- CORE LOGIC ---
def get_entries(channel_or_playlist_url: str, max_videos: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    import yt_dlp
    
    def _normalize_video_entry(e):
        vid = e.get("id")
        if not vid or vid.startswith('@') or len(vid) > 20: return None
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
        webpage_url = url if isinstance(url, str) and url.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
        return {"id": vid, "title": title, "webpage_url": webpage_url, "duration": duration, "upload_date": upload_date, "uploader": uploader}

    def _flatten(obj, out):
        if isinstance(obj, list):
            for it in obj: _flatten(it, out)
        elif isinstance(obj, dict):
            cand = _normalize_video_entry(obj)
            if cand: out.append(cand)
            ents = obj.get("entries")
            if isinstance(ents, list):
                for it in ents: _flatten(it, out)
    
    ydl_opts = {
        "quiet": True, "extract_flat": True, "skip_download": True,
        "nocheckcertificate": True, "ignoreerrors": True,
        "extractor_args": {"youtube": {"tab": ["videos"]}},
    }
    entries = []
    detected_name = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_or_playlist_url, download=False)
            if info:
                detected_name = info.get('uploader') or info.get('channel') or info.get('title')
                _flatten(info, entries)
    except Exception: entries = []

    if len(entries) < 5:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True, "nocheckcertificate": True, "ignoreerrors": True}) as ydl:
                info = ydl.extract_info(channel_or_playlist_url, download=False)
                if info and not detected_name:
                     detected_name = info.get('uploader') or info.get('channel') or info.get('title')
                extra = []
                _flatten(info, extra)
                seen = {e["id"] for e in entries}
                for e in extra:
                    if e["id"] not in seen:
                        entries.append(e)
                        seen.add(e["id"])
        except Exception: pass

    if len(entries) < 5:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "ignoreerrors": True}) as ydl:
                info = ydl.extract_info(channel_or_playlist_url, download=False)
                if info and not detected_name:
                     detected_name = info.get('uploader') or info.get('channel') or info.get('title')
                ch_id = info.get("channel_id") or (info.get("id") if info.get("_type") == "channel" else None)
                if ch_id and ch_id.startswith("UC"):
                    upl_url = f"https://www.youtube.com/playlist?list=UU{ch_id[2:]}"
                    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as ydl:
                        pinfo = ydl.extract_info(upl_url, download=False)
                    upl_entries = []
                    _flatten(pinfo, upl_entries)
                    seen = {e["id"] for e in entries}
                    for e in upl_entries:
                        if e["id"] not in seen:
                            entries.append(e)
                            seen.add(e["id"])
        except Exception: pass

    if max_videos is not None and max_videos > 0: entries = entries[:max_videos]
    if detected_name and "Uploads from" in detected_name:
        detected_name = detected_name.replace("Uploads from ", "")
    return entries, detected_name

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

def scan_existing_ids(out_dir: Path, policy: str, target_fmt: str) -> set:
    exts = [target_fmt.lower()] if policy == "same-format" else ["txt", "json", "srt", "vtt"]
    ids = set()
    for ext in exts:
        for p in out_dir.rglob(f"*.{ext}"):
            name = p.stem
            if len(name) >= 11:
                candidate = name[-11:]
                if re.match(r'^[A-Za-z0-9_-]{11}$', candidate):
                    ids.add(candidate)
                    continue
            m = re.search(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", name)
            if m: ids.add(m.group(1))
    return ids

# --- MERGE CON SPLIT ---
def merge_outputs(out_dir: Path, out_fmt: str, channel_name: str):
    index_file = out_dir / "index.csv"
    if not index_file.exists():
        print("❌ No index.csv found, skipping merge.")
        return

    print("\n🔄 Unificando archivos (Smart Split)...")
    merge_root = Path("full_merges")
    merge_root.mkdir(exist_ok=True)
    
    rows = []
    with index_file.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    valid_rows = [r for r in rows if r['out_file'] and r['out_file'] != '-']
    valid_rows.sort(key=lambda x: x.get('upload_date') or "00000000")

    current_date = datetime.now().strftime("%Y-%m-%d")
    safe_channel = slugify(channel_name)
    
    chunk_idx = 1
    current_chunk_content = []
    current_chunk_size = 0
    total_videos = 0

    def write_chunk(idx, content):
        if not content: return
        fname = f"{safe_channel}_{current_date}_Part{idx:02d}.txt"
        fpath = merge_root / fname
        fpath.write_text("\n".join(content), encoding='utf-8')
        print(f"   📄 Guardado: {fname} ({len(content)} videos)")

    for row in valid_rows:
        fpath = Path(row['out_file'])
        if not fpath.is_absolute(): fpath = out_dir / fpath.name
        
        if fpath.exists():
            try:
                text_content = fpath.read_text(encoding='utf-8')
                vid_date = row.get('upload_date', 'Unknown')
                if len(vid_date) == 8: vid_date = f"{vid_date[:4]}-{vid_date[4:6]}-{vid_date[6:]}"

                header = ["=" * 60, f"VIDEO: {row['title']}", f"DATE:  {vid_date}", f"ID:    {row['video_id']}", f"LINK:  {row['url']}", "=" * 60]
                
                full_entry = "\n".join(header) + "\n" + text_content + "\n\n"
                entry_len = len(full_entry)

                if current_chunk_size + entry_len > MERGE_SPLIT_SIZE:
                    write_chunk(chunk_idx, current_chunk_content)
                    chunk_idx += 1
                    current_chunk_content = []
                    current_chunk_size = 0
                
                current_chunk_content.append(full_entry)
                current_chunk_size += entry_len
                total_videos += 1
            except Exception: pass

    if current_chunk_content:
        write_chunk(chunk_idx, current_chunk_content)

    print(f"✅ MERGE COMPLETADO: {total_videos} videos procesados en {chunk_idx} archivos.")

def fetch_transcript_for_video(video: Dict[str, Any], languages: List[str], out_dir: Path, out_fmt: str, overwrite: bool, translate_to: Optional[str], proxy_config: Any) -> Dict[str, Any]:
    if STOP_EVENT.is_set():
        return {"video_id": video.get("id"), "title": video.get("title"), "url": "", "out_file": None, "upload_date": video.get("upload_date"), "status": "aborted", "message": "Script detenido por bloqueo de IP"}

    from youtube_transcript_api import YouTubeTranscriptApi
    vid = video.get("id") or ""
    title = video.get("title") or ""
    url = video.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    udate = video.get("upload_date") or ""
    safe_title = slugify(title, 120)
    base = f"{safe_title}-{vid}"
    out_path = out_dir / f"{base}.{out_fmt.lower()}"
    res = {"video_id": vid, "title": title, "url": url, "out_file": str(out_path), "upload_date": udate, "status": "", "message": ""}

    if out_path.exists() and not overwrite:
        res["status"] = "skipped"
        res["message"] = "ya existe"
        return res

    try:
        if proxy_config:
            api = YouTubeTranscriptApi(proxy_config=proxy_config)
        else:
            api = YouTubeTranscriptApi()
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
        fetched = transcript.fetch()
        write_output(fetched, out_fmt, out_path)
        res["status"] = "ok"
        return res
    except AttributeError as ae:
        res.update({"out_file": None, "status": "error", "message": f"AttributeError: {ae}"})
        return res
    except Exception as e:
        error_str = str(e)
        if "blocking requests" in error_str or "Too Many Requests" in error_str or "429" in error_str or "Max retries exceeded" in error_str:
            if not STOP_EVENT.is_set():
                STOP_EVENT.set()
                print("\n" + "="*60 + "\n🛑 CRITICAL ERROR: YOUTUBE IP BLOCK DETECTED 🛑\n" + "="*60 + "\n", file=sys.stderr)
            res.update({"out_file": None, "status": "IP_BLOCKED", "message": "YouTube bloqueó la IP"})
            return res
        res.update({"out_file": None, "status": "no_transcript", "message": str(e)})
        return res

# --- MAIN LOGIC WRAPPER ---
def run_downloader(args, is_interactive=False, forced_folder_name=None, auto_mode=False):
    
    proxy_conf = None
    if args.webshare_user and args.webshare_pass:
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            proxy_conf = WebshareProxyConfig(args.webshare_user, args.webshare_pass)
            print("🛡️ Usando Proxy Webshare", file=sys.stderr)
        except: pass
    elif args.proxy:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            proxy_conf = GenericProxyConfig(http_url=args.proxy, https_url=args.proxy)
            print(f"🛡️ Usando Proxy Genérico", file=sys.stderr)
        except: pass
    else:
        print("🔌 Conexión Directa (Sin Proxy)", file=sys.stderr)

    print(f"📋 Listando vídeos de: {args.channel_or_playlist_url}", file=sys.stderr)
    entries, detected_channel_name = get_entries(args.channel_or_playlist_url, args.max)
    base_out_dir = Path(args.outdir).resolve()
    
    if forced_folder_name:
        folder_name = forced_folder_name
        channel_name = forced_folder_name 
    else:
        if detected_channel_name:
            channel_name = detected_channel_name
        else:
            channel_name = "Unknown_Channel"
            if entries:
                first_valid = next((e for e in entries if e.get('uploader') or e.get('channel')), None)
                if first_valid:
                    channel_name = first_valid.get('uploader') or first_valid.get('channel')
        folder_name = slugify(channel_name)

    out_dir = base_out_dir / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    meta_data = {
        "url": args.channel_or_playlist_url,
        "format": args.format,
        "langs": args.languages,
        "translate_to": args.translate_to,
        "include_shorts": args.include_shorts,
        "last_update": datetime.now().isoformat()
    }
    save_channel_meta(out_dir, meta_data)
    index_path = out_dir / "index.csv"
    print(f"📂 Carpeta: {out_dir.name}", file=sys.stderr)

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

    # --- BUCLE DE PERSISTENCIA ---
    while True:
        STOP_EVENT.clear()
        blocked_flag = False
        
        existing_ids = set()
        if args.existing_policy != "none" and not args.overwrite:
            existing_ids = scan_existing_ids(out_dir, args.existing_policy, args.format)

        to_process = [e for e in filtered if e.get("id") not in existing_ids]
        already = [e for e in filtered if e.get("id") in existing_ids]

        print(f"\n🚀 A procesar: {len(to_process)} (Ya descargados: {len(already)})", file=sys.stderr)

        if not to_process:
            print("✅ Nada nuevo que descargar.", file=sys.stderr)
            break

        if args.dry_run:
            print("-- DRY RUN --")
            return out_dir, args.format, folder_name, "OK"

        results = []
        safe_workers = args.workers
        if proxy_conf and safe_workers > 5: safe_workers = 5
        
        with ThreadPoolExecutor(max_workers=max(1, safe_workers)) as ex:
            futures = {
                ex.submit(
                    fetch_transcript_for_video,
                    video=e, languages=args.languages, out_dir=out_dir, out_fmt=args.format,
                    overwrite=args.overwrite, translate_to=args.translate_to, proxy_config=proxy_conf
                ): e for e in to_process
            }
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                
                if res.get('status') == 'IP_BLOCKED':
                    blocked_flag = True

                if res['status'] == 'aborted': continue
                vid_short = res['video_id']
                title_short = (res.get("title") or "")[:40]
                status = res['status']
                msg = f" | {res['message']}" if status != "ok" else ""
                print(f"[{status}] {vid_short} | {title_short}...{msg}")
                
                if STOP_EVENT.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    break

        old_rows = []
        if index_path.exists():
            with index_path.open('r', encoding='utf-8') as f:
                try: old_rows = list(csv.DictReader(f))
                except: pass
        
        final_rows_map = {r['video_id']: r for r in old_rows}
        for e in already:
            if e['id'] not in final_rows_map:
                final_rows_map[e['id']] = {
                    "video_id": e.get("id"), "title": e.get("title"), "url": e.get("webpage_url"),
                    "out_file": str(out_dir / f"{slugify(e.get('title') or '')}-{e.get('id')}.{args.format}"), 
                    "status": "skipped-existing", "message": "omito por politica",
                    "upload_date": e.get("upload_date")
                }
        for r in results: final_rows_map[r['video_id']] = r
        
        with index_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["video_id", "title", "url", "out_file", "status", "message", "upload_date"])
            writer.writeheader()
            for vid in final_rows_map: writer.writerow(final_rows_map[vid])

        if blocked_flag:
            conf = load_global_config()
            if conf.get("ha_url"):
                if auto_mode:
                    print("\n🤖 [AUTO-MODE] Bloqueo detectado. Reiniciando ONT automáticamente...")
                    if trigger_ha_restart(conf):
                        print("\n🔄 Reiniciando el proceso de descarga automáticamente...")
                        continue 
                    else:
                        print("⚠️ Falló el auto-reset. Esperando 5 min antes de reintentar...")
                        time.sleep(300)
                        continue
                else:
                    print("\n" + "!"*60)
                    q = input("🛑 Bloqueo detectado. ¿Reiniciar ONT con Home Assistant y REANUDAR? (s/N): ")
                    if q.lower().strip() == 's':
                        if trigger_ha_restart(conf):
                            print("\n🔄 Reiniciando el proceso de descarga automáticamente...")
                            continue
                    else:
                        print("🛑 Proceso abortado por el usuario.")
                        return out_dir, args.format, folder_name, "ABORT"
            
            print("❌ Proceso detenido por bloqueo (Sin HA configurado).")
            return out_dir, args.format, folder_name, "ABORT"
        else:
            break

    print(f"\n✅ Finalizado: {folder_name}")
    return out_dir, args.format, folder_name, "OK"

# --- INTERACTIVE HELPER ---
def _ask_proxy_interactive():
    config = load_global_config()
    saved_user = config.get("webshare_user")
    print("\n" + "-"*30)
    print("CONFIGURACIÓN DE PROXY")
    if saved_user:
        print(f"1. Usar Webshare GUARDADO ({saved_user})")
        print("2. Webshare (Introducir otro)")
        print("3. Proxy Genérico")
        print("4. Sin proxy (Default)")
        choice = input("Elige (1-4) [4]: ").strip()
        if choice == "1": return saved_user, config.get("webshare_pass"), None
        elif choice == "2":
            u = input("Webshare Username: ").strip()
            p = input("Webshare Password: ").strip()
            if input("¿Guardar estas credenciales? (y/N): ").lower() == 'y': save_global_config({"webshare_user": u, "webshare_pass": p})
            return u, p, None
        elif choice == "3":
            url = input("Proxy URL (http://user:pass@host:port): ").strip()
            return None, None, url
        elif choice == "" or choice == "4": return None, None, None
        else: return None, None, None
    else:
        print("1. Sin proxy (Directo) (Default)")
        print("2. Webshare (User/Pass)")
        print("3. Proxy Genérico")
        choice = input("Elige (1-3) [1]: ").strip()
        if choice == "2":
            u = input("Webshare Username: ").strip()
            p = input("Webshare Password: ").strip()
            if input("¿Guardar estas credenciales? (y/N): ").lower() == 'y': save_global_config({"webshare_user": u, "webshare_pass": p})
            return u, p, None
        elif choice == "3":
            url = input("Proxy URL: ").strip()
            return None, None, url
        elif choice == "" or choice == "1": return None, None, None
        return None, None, None

def _setup_ha_interactive():
    print("\n" + "-"*30)
    print("CONFIGURACIÓN HOME ASSISTANT (Auto Reset Router)")
    url = input("HA URL (http://192.168.x.x:8123): ").strip()
    token = input("Long-Lived Access Token: ").strip()
    script = input("ID del Script (ej: script.reiniciar_ont): ").strip()
    
    if url and token and script:
        save_global_config({"ha_url": url, "ha_token": token, "ha_script_id": script})
        print("✅ Configuración de HA guardada.")
    else:
        print("⚠️ Datos incompletos, no se guardó configuración de HA.")

def _process_update_folder(folder: Path, p_user=None, p_pass=None, p_url=None, auto_mode=False):
    meta = load_channel_meta(folder)
    if not meta.get("url"):
        if auto_mode:
            print(f"⚠️ Salta canal '{folder.name}' (Falta URL, modo auto).")
            return "SKIP"
        print(f"⚠️ El canal '{folder.name}' no tiene URL guardada.")
        url = input(f"Introduce la URL original para '{folder.name}': ")
        meta["url"] = url
        if "format" not in meta: meta["format"] = "txt"
        if "langs" not in meta: meta["langs"] = ["es", "en"]
        save_channel_meta(folder, meta)
    args = SimpleNamespace(channel_or_playlist_url=meta["url"], outdir="channel_transcripts", format=meta.get("format", "txt"), languages=meta.get("langs", ["es", "en"]), include_shorts=meta.get("include_shorts", False), translate_to=meta.get("translate_to"), existing_policy="same-format", overwrite=False, workers=8, max=None, since=None, until=None, dry_run=False, webshare_user=p_user, webshare_pass=p_pass, proxy=p_url)
    _, _, _, status = run_downloader(args, is_interactive=True, forced_folder_name=folder.name, auto_mode=auto_mode)
    return status

# --- INTERACTIVE MENU ---
def interactive_menu():
    clear_screen()
    print("\n" + "="*50 + "\n   📺 YOUTUBE TRANSCRIPTS MANAGER v3.2\n" + "="*50)
    base_dir = Path("channel_transcripts")
    base_dir.mkdir(exist_ok=True)
    print("1. 🔄 Actualizar un canal existente")
    print("2. 🚀 Actualizar TODOS los canales")
    print("3. ➕ Añadir un nuevo canal")
    print("4. 🏠 Configurar Home Assistant")
    print("5. 📚 Re-Merge & Split (Unificar y Dividir)")
    print("6. 🔌 Resetear ONT (HA)")
    print("7. ♾️  MODO AUTO DESATENDIDO (Loop + Auto Reset)")
    print("0. ❌ Salir")
    opt = input("\nElige una opción: ").strip()
    
    if opt == "0":
        clear_screen(); sys.exit(0)
    elif opt == "4":
        _setup_ha_interactive()
    elif opt == "6":
        conf = load_global_config()
        trigger_ha_restart(conf)
    elif opt == "5":
        folders = [f for f in base_dir.iterdir() if f.is_dir()]
        print(f"\nSe procesarán {len(folders)} canales para Merge/Split...")
        for f in folders:
            print(f">>> Procesando: {f.name}")
            meta = load_channel_meta(f)
            merge_outputs(f, meta.get('format', 'txt'), f.name)
        input("\n✅ Completado. Enter para volver...")
        
    elif opt == "7":
        folders = [f for f in base_dir.iterdir() if f.is_dir()]
        print(f"\n♾️ INICIANDO MODO DESATENDIDO EN {len(folders)} CANALES...")
        print("⚠️  Asegúrate de tener HA configurado. El script reiniciará el router automáticamente.")
        input("Presiona Enter para comenzar...")
        pu, pp, purl = None, None, None
        for f in folders:
            print(f"\n>>> [AUTO] Procesando: {f.name}")
            _process_update_folder(f, pu, pp, purl, auto_mode=True)
        print("\n✅ CICLO AUTO COMPLETADO.")

    elif opt == "1":
        folders = [f for f in base_dir.iterdir() if f.is_dir()]
        if not folders: print("No hay canales."); input("Enter..."); return interactive_menu()
        print("\nCanales disponibles:")
        for i, f in enumerate(folders, 1): print(f"  {i}. {f.name}")
        try:
            sel_input = input("\nNúmero del canal (0 vuelve): ")
            if sel_input == "0": return interactive_menu()
            sel = int(sel_input)
            target_folder = folders[sel-1]
        except: return interactive_menu()
        pu, pp, purl = _ask_proxy_interactive()
        _process_update_folder(target_folder, pu, pp, purl)
        q = input("\n¿Hacer Merge de este canal ahora? (y/N): ")
        if q.lower() == 'y':
            meta = load_channel_meta(target_folder)
            merge_outputs(target_folder, meta.get('format', 'txt'), target_folder.name)
    elif opt == "2":
        folders = [f for f in base_dir.iterdir() if f.is_dir()]
        print(f"\nSe van a actualizar {len(folders)} canales...")
        pu, pp, purl = _ask_proxy_interactive()
        for f in folders:
            print(f"\n>>> Actualizando: {f.name}")
            status = _process_update_folder(f, pu, pp, purl)
            if status == "ABORT":
                print("\n🛑 Actualización masiva cancelada por el usuario.")
                break
        if status != "ABORT": print("\n✅ Todos los canales actualizados.")
    elif opt == "3":
        url = input("URL del canal/playlist: ")
        fmt = input("Formato [txt]: ") or "txt"
        langs = input("Idiomas [es en]: ") or "es en"
        shorts = input("¿Shorts? (y/N): ").lower() == 'y'
        pu, pp, purl = _ask_proxy_interactive()
        args = SimpleNamespace(channel_or_playlist_url=url, outdir="channel_transcripts", format=fmt, languages=langs.split(), include_shorts=shorts, existing_policy="same-format", overwrite=False, workers=8, max=None, since=None, until=None, translate_to=None, dry_run=False, webshare_user=pu, webshare_pass=pp, proxy=purl)
        out_d, out_f, c_name, _ = run_downloader(args, is_interactive=True)
        q = input("\n¿Merge? (y/N): ")
        if q.lower()=='y': merge_outputs(out_d, out_f, c_name)
    else: return interactive_menu()
    input("\nPresiona Enter para volver al menú...")
    interactive_menu()

def main():
    _ensure_deps()
    if len(sys.argv) == 1:
        try: interactive_menu()
        except KeyboardInterrupt: sys.exit(0)
        return
    # CLI Mode omitted
    pass

if __name__ == "__main__":
    main()