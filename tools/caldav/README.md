# CalDAV Setup For iCloud Appointments

This workspace uses the OpenClaw `caldav-calendar` skill pattern:

1. Install `vdirsyncer` and `khal`.
2. Store the Apple app-specific password locally, not in chat.
3. Discover/sync iCloud CalDAV calendars.
4. Query the synced calendars with `khal`.

## Preferred Install

System install, if sudo is allowed:

```bash
sudo apt-get install -y vdirsyncer khal
```

User/workspace install, if network access is allowed:

```bash
python3 -m venv .venvs/caldav
.venvs/caldav/bin/pip install vdirsyncer khal
```

## Credential

Create an Apple app-specific password at Apple ID settings. Do not paste it in chat.

Store it locally:

```bash
mkdir -p ~/.config/vdirsyncer
printf '%s\n' 'APPLE_APP_SPECIFIC_PASSWORD_HERE' > ~/.config/vdirsyncer/icloud_password
chmod 600 ~/.config/vdirsyncer/icloud_password
```

## Config Files

Copy and edit the templates:

```bash
mkdir -p ~/.config/vdirsyncer ~/.config/khal
cp tools/caldav/vdirsyncer.config.template ~/.config/vdirsyncer/config
cp tools/caldav/khal.config.template ~/.config/khal/config
```

Then replace `APPLE_ID_EMAIL_HERE` with the iCloud/Apple ID email.

## Discover And Sync

```bash
vdirsyncer discover
vdirsyncer sync
khal list today 7d
khal search appointments --format "{start-date} {start-time}-{end-time} {title} [{calendar}]"
```

If using the workspace venv instead of system packages:

```bash
.venvs/caldav/bin/vdirsyncer discover
.venvs/caldav/bin/vdirsyncer sync
.venvs/caldav/bin/khal list today 7d
```
