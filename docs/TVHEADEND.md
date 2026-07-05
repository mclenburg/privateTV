# tvheadend integration

PrivateTV is designed to be consumed by tvheadend as an IPTV Automatic Network.

PrivateTV endpoints:

```text
http://<PRIVATE-TV-HOST>:9988/playlist.m3u
http://<PRIVATE-TV-HOST>:9988/xmltv.xml
http://<PRIVATE-TV-HOST>:9988/stream/main.ts
http://<PRIVATE-TV-HOST>:9988/stream/hazard.ts   optional Hazard TV
```

If tvheadend runs on the same Raspberry Pi, use:

```text
http://127.0.0.1:9988/playlist.m3u
http://127.0.0.1:9988/xmltv.xml
```

If other devices consume the playlist directly, configure `server.public_base_url` with the Pi's LAN IP or hostname.

## 1. Create the IPTV Automatic Network

Open tvheadend:

```text
http://<RASPBERRY-PI>:9981
```

Go to:

```text
Configuration → DVB Inputs → Networks → Add
```

Choose:

```text
IPTV Automatic Network
```

Suggested values:

```text
Network name: PrivateTV
URL:          http://127.0.0.1:9988/playlist.m3u
Max input streams: 4
```

Save. tvheadend should fetch the M3U and create a mux/service for PrivateTV. If Hazard TV is enabled, it will create a second service.

## 2. Map services to channels

Go to:

```text
Configuration → DVB Inputs → Services
```

Find the PrivateTV service and map it to a channel.

Then check:

```text
Configuration → Channel / EPG → Channels
```

The channel should exist and be playable.

## 3. XMLTV EPG via internal grabber script

Create a simple XMLTV grabber:

```bash
sudo tee /usr/local/bin/tv_grab_privatetv > /dev/null <<'SH'
#!/bin/sh

case "$1" in
  --description)
    echo "PrivateTV XMLTV"
    exit 0
    ;;
  --capabilities)
    echo "baseline"
    exit 0
    ;;
  --version)
    echo "1.0"
    exit 0
    ;;
esac

curl -fsS http://127.0.0.1:9988/xmltv.xml
SH

sudo chmod +x /usr/local/bin/tv_grab_privatetv
```

Test it:

```bash
/usr/local/bin/tv_grab_privatetv --description
/usr/local/bin/tv_grab_privatetv | head -20
```

In tvheadend go to:

```text
Configuration → Channel / EPG → EPG Grabber Modules
```

Enable:

```text
Internal: XMLTV: PrivateTV XMLTV
```

Then trigger the internal grabber:

```text
Configuration → Channel / EPG → EPG Grabber
```

Use the available rerun/trigger button for internal grabbers.

## 4. XMLTV via external socket

tvheadend can also accept XMLTV over its external XMLTV socket.

Enable in tvheadend:

```text
Configuration → Channel / EPG → EPG Grabber Modules → External: XMLTV
```

Find the socket:

```bash
sudo find /home/hts/.hts /var/lib/tvheadend -path '*xmltv.sock' -ls 2>/dev/null
```

Typical path:

```text
/var/lib/tvheadend/epggrab/xmltv.sock
```

Inject XMLTV:

```bash
curl -fsS http://127.0.0.1:9988/xmltv.xml | socat - UNIX-CONNECT:/var/lib/tvheadend/epggrab/xmltv.sock
```

Use the actual socket path found on your system.

## 5. Channel ID matching

The M3U `tvg-id` and XMLTV channel id must match.

Check M3U:

```bash
curl -s http://127.0.0.1:9988/playlist.m3u | head -40
```

Check XMLTV:

```bash
curl -s http://127.0.0.1:9988/xmltv.xml | grep -E '<channel|channel=' | head -20
```

The IDs should be the same, for example:

```text
privatetv
```

## 6. Playback diagnosis

Test PrivateTV directly:

```bash
ffplay -fflags nobuffer -flags low_delay http://127.0.0.1:9988/stream/main.ts
```

Test through tvheadend by using the play/stream link in the tvheadend web UI. If direct PrivateTV and the tvheadend web stream are smooth, but Kodi stutters, the issue is likely Kodi, pvr.hts, audio output, or local playback configuration rather than PrivateTV.

Useful load checks while Kodi is playing:

```bash
echo "--- throttling ---"
vcgencmd get_throttled 2>/dev/null || true
echo "--- temp ---"
vcgencmd measure_temp 2>/dev/null || true
echo "--- load ---"
uptime
echo "--- top cpu ---"
ps -eo pid,comm,%cpu,%mem,args --sort=-%cpu | head -15
```

Kodi audio-renderer errors such as these point to audio output rather than stream generation:

```text
ActiveAE::MakeStream - could not create stream
ProcessDecoderOutput - failed to create audio renderer
OutputPicture - timeout waiting for buffer
```

For PulseAudio/PipeWire diagnostics:

```bash
pactl info
pactl list short sinks
pactl list short sink-inputs
```

## 7. Useful logs

PrivateTV:

```bash
journalctl -u privatetv.service -b --no-pager | tail -120
```

tvheadend:

```bash
journalctl -u tvheadend -b --no-pager | tail -160
```

Kodi:

```bash
grep -Ei "error|warning|buffer|cache|drop|skip|discontinu|pvr|htsp|audio|video|ffmpeg" /home/pi/.kodi/temp/kodi.log | tail -120
```

