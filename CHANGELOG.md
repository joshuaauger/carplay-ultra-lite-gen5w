# Changelog

Versions after 1.0.0 are test builds running on one car (Hyundai Ioniq 6, US, firmware 260507). 1.3.3 is published as a test build (an update for a car on 1.0.0); the main release is still 1.0.0.

## 1.1.13 (2026-11-17, fork: Ioniq 6 CEEV 260903, not yet tried in the car)

- **The picture keeps up with the sound.** The sound comes from the phone and plays on while the car's picture stalls to load, so each stall used to leave the picture that much behind. The car now keeps a clock of where the sound is: a picture behind it plays slightly faster (up to 1.25×, which can't be heard since the car's player has no sound) until it catches up, and one more than 8 seconds behind jumps straight to the sound when that part is already loaded. It only speeds up with 5 seconds loaded ahead, so catching up doesn't cause another stall. Pauses and seeks, the phone's and the car's, move the clock with them.
- **Network errors are retried.** A failed load is tried 8 times before the player gives up, then the player tries again from where it was, 1, 2, 4, 8 and 16 seconds later, showing the spinner rather than an error.
- **The phone's sound stops when the video can't play.** After an error, or when the video is closed while loading, the phone is told the video is paused. Before, an error that came while loading left the sound playing on indefinitely.
- HLS streams start at a low quality and step up as the connection allows (the head unit sees Wi-Fi, but it's the phone's mobile data).
- The video trace records every 5 seconds how far the picture is behind the sound and the speed it plays at.

## 1.1.12 (2026-11-17, fork: Ioniq 6 CEEV 260903, not yet tried in the car)

- **Fix: the video controls vanished once the video started**, leaving no way back to CarPlay. The head unit draws the video's picture over everything else in its window, so the controls now have a window of their own above the picture's: close, play/pause, skip and the seek bar stay reachable, and a tap brings them back after they fade.

## 1.1.11 (2026-11-17, fork: Ioniq 6 CEEV 260903, not yet tried in the car)

- **Video recordings on the USB stick:** make a folder named `CarPlayUltraLite-Video` at the top of a USB stick and leave it plugged in. Every 30 seconds the mod copies the phone's recorded settings and overlay streams into `side/` and the video engine's trace into `trace/`. Only sticks with that folder get anything; nothing is read from the stick.
- The recordings are kept per CarPlay start (`0001-…`, `0002-…`, the newest five), so a restart no longer overwrites them.

## 1.1.10 (2026-11-17, fork: Ioniq 6 CEEV 260903, not yet tried in the car)

- **New video controls:** the plain "Back to CarPlay" and "Play / Pause" text is replaced by controls in the style of Apple's players: a close button, a big play/pause with 10-second skip back and forward, a seek bar with the elapsed and remaining time and what's loaded, a loading spinner, and messages when a video can't play. They fade out after 4 seconds while playing; tap to bring them back, double-tap the left or right third of the screen to skip.
- **Picture fit:** a button at the top right switches between the whole picture, filling the screen (edges cut off) and stretching. The choice is kept.
- **Subtitles:** the CC button goes through the video's subtitle tracks and off. Subtitles start off.
- **The phone's video side streams are recorded:** the phone opens a "settings" and an "overlay" stream for every video, and nobody knows what they carry yet. The car now decrypts both (ports 7138 and 7139, only while "Video playback in CarPlay" is on) and records every package in DiPO's `files/cpc-video-side/`. Nothing is acted on. Native recipe rebuilt for libCarPlayCore ef49c09b (CEEV.CAN 260903) only; the d3a47296 recipe (US 260507, CAN 250818/260206) still sends both streams to the old sink.

## 1.1.9 (2026-11-16, fork: Ioniq 6 CEEV 260903)

- **Video on cars with the whitelist firewall (Ioniq 6):** the video engine connects out to the iPhone's video proxy, on a port the phone picks each time; the stock firewall drops outgoing traffic on the hotspot, so playback failed with "tunnel: failed to connect … after 8000ms" and the car stayed on Now Playing. Two network rules (only while "Video playback in CarPlay" is on): outgoing TCP to the hotspot's addresses, and the replies.

## 1.3.3 (2026-11-10, in testing)

- **Experiment "Only CarPlay's volume slider in CarPlay"** (off by default): while CarPlay is on the screen, the volume knob and the steering wheel's volume buttons change the volume without the head unit's volume pop-up, so only CarPlay's slider shows.
  - The knob's speed is kept: a fast spin moves as many steps as it does outside CarPlay.
  - CarPlay's slider is told at once when a key changes the volume.
  - The mute button stays the car's own; its pop-up is dismissed straight afterwards. Known issue: the pop-up still flashes for a moment.
  - Anything unexpected leaves the key to the car, so the volume keys keep working as stock.

## 1.2.x (2026-11-10, in testing)

- **Car volume in CarPlay:** CarPlay's Volume page shows the head unit's real levels for media, navigation, phone and Siri, follows the knob and the steering wheel, and sets the car's volume. The phone can't change a level before it has been shown the car's own one, so nothing jumps.
- **Vehicle notifications:** the Vehicle app's notification list is filled by the car; an entry you dismiss stays dismissed. One test entry is posted at each start.
- **Readings match the cluster:** battery, range and odometer are rounded down as the instrument cluster does.
- CarPlay's Radio app: its play and source buttons open the head unit's own radio (the app itself still has no stations).

## 1.1.x (2026-11-10, in testing)

- **The car's page in CarPlay's Vehicle app:** battery level, range and odometer; a Car home screen button; a Battery preconditioning switch (through Launchpad); the Light Vibes switch and button; buttons for HMG-API, NEMESIS Manager, Radio, EV and Vehicle settings.
- Found on the way: the iPhone builds the Vehicle app from the description it is given when CarPlay connects, so the page is part of that description.

## 1.0.0 (2026-11-08)

- Climate in CarPlay, both ways, with a panel for each seat.
- The CarPlay Ultra theme with its wallpapers and Themes page.
