# Memory

A local task, notes and planning app built around a see-through, 3D electronic brain. It's meant to replace Microsoft To Do, Planner and OneNote in one place.

- **Basket.** New tasks, and anything synced from Microsoft Planner, land here first.
- **Synapses (RAM slots).** Drag a task onto the brain to work on it. Only a limited number of slots exist (7 by default). The most pressing work sits at the **front** of the brain. **Logical** work goes on the left hemisphere, **creative** work on the right, and an odd slot count adds a central *executive* slot.
- **Backlog queue.** Everything that doesn't fit waits here, ordered by priority score. When a synapse frees up (a task is completed or deleted), the top of the queue moves in automatically.
- **Synapse details.** Click any synapse or task to open a To Do-style drawer. It holds steps, My Day, reminders, due dates, repeat, priority, effort, completion week, a logical↔creative slider and tags. It also has OneNote-style rich notes: headings, lists, to-do checkboxes, code, links and inline images. You can attach files and **paste screenshots with Ctrl+V**.
- **Growth.** A synapse grows dendrites as you add notes, steps, files and links. Related tasks are joined by thin glowing axons.
- **Hemispheres.** Colour comes from where a synapse sits: blue logical work on the left, pink creative work on the right, and the centre slot shows the task's own kind. Auto-placement keeps each kind on its own side and leaves a slot empty rather than put work on the wrong side. Dragging a task onto the other hemisphere re-classifies it.
- **Sequences.** In a task's **Sequence** card, mark what it *needs first* and what it *unlocks*. Each chain is numbered in completion order: step 1, 2, 3… up to the goal. On the brain, thick axons carry impulses from each step toward the one it unlocks, and labels read "Step 2 of 3 → goal". Prerequisites inherit the urgency of whatever waits on them. Loops are refused.
- **Auto-scheduling.** Every task gets an estimated completion week. The estimate is based on priority, due date, effort and your weekly capacity. Tasks that can't fit before their due date are flagged *at risk*.
- **Dashboard.** It shows KPI tiles, a week-by-week task layout, planned hours vs capacity, a due-date calendar, the thinking balance and a completed-vs-added trend.
- **Claude.** Chat about your tasks, and Claude can create, update and complete tasks, set reminders and move work on or off the brain. **Delegate with AI** proposes a synapse allocation that you approve before anything changes. Claude can also write daily briefings and per-task insights.
- **Notifications, per task.** Each task's pop-up has a **Notify** setting: Desktop (the default), Email, Both or Off. Desktop alerts are native Windows notifications sent by the Memory server, so they arrive even with no Memory window open; clicking one opens the task. Email goes through Outlook to your Microsoft account, or to another address set in Settings → *Notifications*, which also has a test button.
- **Templates.** Use the template button in the quick-add box, or the template chips in a desktop **+ New task** pop-up. Built-ins: Meeting prep, Weekly report, Bug fix, Creative brief and Email follow-up. Any task can become a template with **Save as template** in its pop-up; that keeps its steps, notes, priority, effort, tags, repeat, notifications and how far out it's due.
- **Inbox.** The right-hand pane has **Tasks | Inbox** tabs. Inbox shows your Outlook mail. **→ Task** has Claude read the email and create a basket task with a title, summary, due date, priority, effort and steps, plus a link back to Outlook. **Suggest** asks Claude which emails need action at all. Without a Claude key, the task is made from the subject and body. Emails are treated as data, so instructions inside them are ignored. The desktop wallpaper shows a compact inbox top-right.
- **Arrange.** Click **Arrange** above the brain and drag synapses to new spots. Each one slides along its own hemisphere, so its logical/creative side never changes. Positions are saved, the wallpaper uses them too, and **Reset layout** puts them back.
- **Colour themes.** Settings → *Colour theme* re-tints the whole interface and the brain: Neural blue, Teal, Synapse green, Gold, Ember orange, Coral red, Violet or Graphite. The change applies instantly in every open window, including the desktop wallpaper. Logical/creative and due-date colours never change, so they keep their meaning.

## Install

Download **Memory-Setup-x.y.z.exe** from the repository's **Releases** page and run it. No admin rights or Python are needed.

- **Where it goes:** the app installs to `%LOCALAPPDATA%\Programs\Memory` and adds **Memory** to the Start menu.
- **Auto-start:** Memory starts silently when you sign in, through a Task Scheduler task that also restarts it within 5 minutes if it ever stops. This is a ticked option in the installer.
- **Your data** lives in `%LOCALAPPDATA%\Memory` (tasks, notes, files, settings, `server.log`), so updates never touch it. Uninstalling, from Windows Settings → Apps, asks whether to delete it too.
- **Updates:** run the newer installer, which replaces the app in place. Memory shows a notice when a new release is out. While the repository is private, GitHub hides its releases from that check, so it stays quiet until the repository is public.
- **Security warning:** the installer isn't code-signed, so Windows may show "Windows protected your PC" the first time. Choose **More info → Run anyway**.

A portable zip is also attached to each release. Unzip it anywhere and run `Memory.exe --open`.

## Run from source

```bash
python -m pip install -r requirements.txt
```

```bash
python launcher.pyw --open
```

That starts the server at http://localhost:8765 and opens it in your browser. From source, data is stored in `data/` next to the code.

To start it when you sign in, run the command below. It sets up the same Task Scheduler task as the installer plus a Start menu shortcut; add `-Remove` to undo it. Server output goes to `data/server.log`.

```bash
powershell -ExecutionPolicy Bypass -File scripts\startup.ps1
```

### Use the brain as your desktop wallpaper

Memory can put the brain on your desktop itself, behind your icons and on every screen. No other app is needed. Turn it on in **Settings → Desktop wallpaper** (or from the welcome screen), and choose **All screens** or **Main screen only**.

- **How it works:** one borderless Edge window per screen shows `http://localhost:8765/?wallpaper`, slotted into Windows' desktop layer between your icons and the normal wallpaper. Both the newer Windows 11 (24H2+) desktop and the classic one are supported.
- **Clicking:** mouse movement, clicks, drags and the scroll wheel over the bare desktop are passed through to the brain. Over any other window, nothing is passed through.
- **Pausing:** a screen's brain stops drawing while a maximised or full-screen window covers it, and while a Memory pop-up is open.
- **Restarts:** if Explorer restarts, the wallpaper rebuilds itself. If Lively Wallpaper is running, Memory gives the desktop to it, so close or uninstall Lively to use the built-in one.
- **Profile:** the wallpaper windows use their own small Edge profile, `wallpaper-profile` in the data folder.

You can still use [Lively Wallpaper](https://www.rocksdanister.com/lively/) instead: leave the setting off, then in Lively choose **+ Add Wallpaper** and paste `http://localhost:8765/?wallpaper`.

Working from the desktop (the wallpaper only gets mouse input, so typing happens in pop-up windows):

| On the wallpaper | What happens |
|---|---|
| Click a synapse | A quick card: tick steps, read notes, **✓ Complete**, **Pin**, **To queue**, or **Open ↗** |
| **Open ↗** or click the notes | A pop-up window opens over the desktop with the full task editor: notes, steps, dates, files and Ctrl+V screenshots. **Esc** or ✕ closes it |
| Click an empty synapse | Pick a basket or queue task to fill it, or **+ New task…** |
| Drag a synapse | Drop it on another synapse, or on **Basket**, **Queue** or **✓ Complete** |
| **+ New task** / **Open Memory** (summary card, bottom-right) | A pop-up to capture a task, or the full app in its own window |

The wallpaper also shows a translucent readout of your computer in the top-left: name, Windows version, CPU, GPU, RAM and disk, plus live CPU, RAM, GPU, disk, network, uptime and battery. It's read from Windows' own counters, sampled every 2 s only while something is showing it. Your **quick links** sit in the bottom-left; edit them in Settings → *Quick links*. They can be web addresses, app links (`ms-teams:`) or file and folder paths (`C:\Reports`, `~\Downloads`), and they also appear at the bottom of the app's left rail.

While a Memory pop-up or app window is open, the wallpaper brain holds still and stops drawing, so moving those windows never spins it. On large screens the brain renders at a capped resolution and is scaled up, which keeps integrated graphics comfortable.

Pop-ups are Edge (or Chrome) app windows with no tabs or address bar. Only one is open at a time, since opening another closes the previous one. They use their own small browser profile in `data/app-window-profile`, so they always open centred and at a set size. Reminders appear as toasts on the wallpaper, and **Open** brings up the task.

### Links to a task

Any task opens directly at `http://localhost:8765/#task=<id>`. The address bar updates while a task is open, so you can bookmark it or paste the link into a note.

## Connect Claude

1. Get an API key from https://console.anthropic.com.
2. Open **Settings** (the gear icon) and paste the key under *Claude*. You can also put `ANTHROPIC_API_KEY=...` in a `.env` file (copy `.env.example`).
3. Pick a model. The default is Claude Opus 5.5; Sonnet 5.5 and Haiku 5.5 are cheaper and faster.

Requests to Opus 5.5, Sonnet 5.5, Opus 5 and Fable 5.1 enable Anthropic's server-side refusal fallback (`fallbacks: "default"`). If one of those models declines a request, the API retries it on a fallback model automatically.

## Connect Microsoft Planner and Outlook

Planner sync uses Microsoft Graph with a device-code sign-in. Register an app once:

1. In the Azure portal, open **Microsoft Entra ID → App registrations → New registration**. Name it "Memory" and choose *Accounts in this organizational directory only* (or multitenant if you prefer). Leave the redirect URI blank.
2. Under **Authentication**, click **Add a platform → Mobile and desktop applications** and add the custom redirect URI `http://localhost`. Then, under **Advanced settings**, set **Allow public client flows** to **Yes**. No client secret is needed.
3. Under **API permissions → Add a permission → Microsoft Graph → Delegated**, add `Tasks.ReadWrite`, `User.Read`, `Mail.Read` and `Mail.Send`. The mail permissions power the Inbox tab and email notifications. If your tenant requires it, ask an admin to **Grant admin consent**.
4. Copy the **Application (client) ID** and **Directory (tenant) ID** into Settings → *Microsoft Planner & Outlook*, then click **Sign in with Microsoft**. A Microsoft sign-in page opens in your browser. If your organisation allows device-code sign-in, **Use a sign-in code instead** works too.

Once you're signed in:

- **Pull.** Planner tasks assigned to you arrive in the **Basket**, with their plan, bucket, description, checklist, priority and due date. Each plan also appears as a list in the left rail.
- **Push.** Completing a Planner task, ticking its checklist, or changing its title, priority or due date writes the change back to Planner.
- **Schedule.** Sync runs every 15 minutes, or on demand with the **Planner** button.

### Sync Planner with Power Automate (one-way, no Azure app needed)

If your organisation won't allow an app registration, a Power Automate cloud flow can push your active Planner tasks to Memory instead: **Recurrence → List my tasks → Filter array (`percentComplete` < 100) → Select → HTTP**.

**What a sync does**

- **New tasks:** the flow sends a full snapshot of your active Planner tasks. Each one that's new to Memory is created in the **Basket**, with `source = "planner"` and `external_id` set to the Planner ID. Memory's own task IDs stay separate, and `(source, external_id)` is unique, so running the flow again never makes duplicates.
- **Known tasks:** their Planner fields are updated: title, percent complete, priority, due date, start date, plan ID and bucket ID. Notes, steps, files, links, tags and synapse placement are yours and are never touched, and unchanged tasks are skipped. Each task records `last_synced_at` in UTC.
- **Removals:** Planner tasks that Memory still shows as open but that are missing from the snapshot were completed or removed in Planner. They're **archived**, meaning marked done and flagged, never deleted. If one becomes active in Planner again, it's restored.
- **Your decisions win:** tasks you completed yourself in Memory stay completed, and tasks you created in Memory are never affected.
- **Empty snapshots:** a snapshot with no tasks archives nothing, in case the flow misfired. Add `?allow_empty=true` to the URL if you really want that.
- **One-way only:** nothing is ever written back to Planner. In Memory, these tasks show a small Planner note, and their title, due date and priority are read-only.

**Set up the token**

Run this once. It saves a random token as `MEMORY_PLANNER_SYNC_TOKEN` in `%LOCALAPPDATA%\Memory\.env`, copies it to your clipboard without showing it, and restarts Memory. Run it again to replace the token.

```bash
powershell -ExecutionPolicy Bypass -File scripts\new-sync-token.ps1
```

The token is only ever read from the environment or that `.env` file. It isn't stored in the database, shown in the app or written to the log. Settings → *Microsoft Planner & Outlook* only shows whether it's set, along with the last sync.

**The flow's HTTP action**

| Field | Value |
|---|---|
| Method | `POST` |
| URI | `https://<your-tunnel-host>/api/planner/sync` |
| Headers | `Content-Type: application/json` and `Authorization: Bearer <token>` |
| Body | `{"tasks": @{body('Select')}}` |

Responses:

- **200** with `{"success": true, "received", "created", "updated", "unchanged", "archived", "restored", "kept_done", "warnings", "synced_at"}`.
- **400** for malformed data, with details.
- **401** for a missing or wrong token, and **429** after repeated wrong tokens.
- **413** if the request is over 2 MB.
- **415** if it isn't JSON.
- **503** if no token is configured.

**Reaching your PC from the cloud**

Memory only listens on `127.0.0.1`, so a cloud flow can't reach it directly. You need an HTTPS tunnel to `http://localhost:8765`, for example [Microsoft Dev Tunnels](https://learn.microsoft.com/azure/developer/dev-tunnels/), Cloudflare Tunnel or ngrok. Requests that arrive through a tunnel, or from any other website, can only reach `POST /api/planner/sync`, and only with the token; the rest of Memory stays local. Check with IT before exposing a work PC to the internet.

**Test it locally**

Once the token is set, this posts a sample Planner task using the token from your `.env`. Every request is a full snapshot, so this archives any other Planner tasks Memory has from earlier syncs; the next real sync restores them.

```bash
powershell -Command "$t = (Get-Content $env:LOCALAPPDATA\Memory\.env | Select-String '^MEMORY_PLANNER_SYNC_TOKEN=').Line.Split('=',2)[1]; Invoke-RestMethod -Method Post http://localhost:8765/api/planner/sync -Headers @{Authorization = \"Bearer $t\"} -ContentType 'application/json' -Body '{\"tasks\":[{\"id\":\"KGEFAhIzkUu2r_CGbNO6VmUADrzz\",\"title\":\"Microsoft Update Catalog Ingestion\",\"percentComplete\":0,\"priority\":5,\"dueDate\":\"2026-10-15T10:00:00Z\",\"startDate\":null,\"planId\":\"oM7TZEj9TUivltGR1o1682UAH2h9\",\"bucketId\":\"nRXbhxBR-EiMvRhRXledDGUACBIX\"}]}'"
```

## Using it

| Action | How |
|---|---|
| Capture a task | Type in the box at the top of the right-hand list and press Enter |
| Put a task on the brain | Drag it from a list or the queue onto a synapse. Click an empty synapse to pick one. Or use **Place on brain** in its drawer |
| Take a task off the brain | Drag the synapse down to the queue, basket or **✓ Complete** target |
| Let Memory decide | **Sort basket** moves basket tasks onto the brain or into the queue. **Re-think** re-allocates synapses by priority and keeps pinned ones |
| Let Claude decide | **Delegate with AI**, then review and **Apply to brain** |
| Search | Ctrl+K |

## Development

```bash
python -m pytest tests
```

- `backend/`: FastAPI app (`app.py`), SQLite storage (`db.py`), scheduling engine (`engine.py`), classifier, Claude service, Planner/Outlook sync, notifications, the reminder/background loop and the launcher (`launcher.py`, the entry point `Memory.exe` is built from). `paths.py` decides where data lives, and `version.py` holds the version number.
- `frontend/`: a no-build ES-module app. The Three.js brain is in `js/brain3d.js`, the task pop-up in `js/taskPanel.js` and the dashboard in `js/dashboard.js`. Three.js r170 is vendored in `frontend/vendor/`.
- `packaging/memory.iss`: the Inno Setup installer script. `scripts/build.ps1` builds the app with PyInstaller, plus the portable zip and installer, into `dist/`.
- `.github/workflows/`: `tests.yml` runs the tests on every push to `main`; `release.yml` builds and publishes a release when a version tag is pushed.

### Shipping an update

1. Make your changes, run the tests, and commit them.
2. Run one command. It bumps the version, tags it and pushes:
   ```bash
   powershell -ExecutionPolicy Bypass -File scripts\release.ps1
   ```
   Use `-Bump minor` for new features or `-Bump major` for big changes; the default is a patch (1.0.0 → 1.0.1).
3. GitHub Actions runs the tests, builds `Memory-Setup-x.y.z.exe` and publishes the release. This takes about 5 minutes; watch it in the repository's **Actions** tab. People with Memory installed see the update notice once the repository is public.

To try a build locally first, run `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`. It needs Inno Setup 6 for the installer step: `winget install JRSoftware.InnoSetup`.

Third-party licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
