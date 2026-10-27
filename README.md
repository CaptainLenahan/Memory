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

`http://localhost:8765/?wallpaper` is a brain-only view: no sidebars or buttons, just a small summary card in the bottom-right, with a lower frame rate. Show it as a live wallpaper with the free [Lively Wallpaper](https://www.rocksdanister.com/lively/) app (Microsoft Store, or `winget install rocksdanister.LivelyWallpaper`):

1. Make sure Memory starts at sign-in (above).
2. In Lively, click **+ Add Wallpaper**, paste `http://localhost:8765/?wallpaper` into the URL box, then press → and **OK**.
3. Select the new wallpaper and apply it to your screen(s).

Working from the desktop (Lively only passes mouse clicks to the wallpaper, so typing happens in pop-up windows):

| On the wallpaper | What happens |
|---|---|
| Click a synapse | A quick card: tick steps, read notes, **✓ Complete**, **Pin**, **To queue**, or **Open ↗** |
| **Open ↗** or click the notes | A pop-up window opens over the desktop with the full task editor: notes, steps, dates, files and Ctrl+V screenshots. **Esc** or ✕ closes it |
| Click an empty synapse | Pick a basket or queue task to fill it, or **+ New task…** |
| Drag a synapse | Drop it on another synapse, or on **Basket**, **Queue** or **✓ Complete** |
| **+ New task** / **Open Memory** (summary card, bottom-right) | A pop-up to capture a task, or the full app in its own window |

The wallpaper also shows a translucent readout of your computer in the top-left: name, Windows version, CPU, GPU, RAM and disk, plus live CPU, RAM, GPU, disk, network, uptime and battery. It's read from Windows' own counters, sampled every 2 s only while something is showing it. Your **quick links** sit in the bottom-left; edit them in Settings → *Quick links*. They can be web addresses, app links (`ms-teams:`) or file and folder paths (`C:\Reports`, `~\Downloads`), and they also appear at the bottom of the app's left rail.

While a Memory pop-up or app window is open, the wallpaper brain holds still and stops drawing, because Lively keeps forwarding mouse movement even when another window has focus. On large screens the brain renders at a capped resolution and is scaled up, which keeps integrated graphics comfortable.

Pop-ups are Edge (or Chrome) app windows with no tabs or address bar. Only one is open at a time, since opening another closes the previous one. They use their own small browser profile in `data/app-window-profile`, so they always open centred and at a set size. Reminders appear as toasts on the wallpaper, and **Open** brings up the task. Lively pauses the wallpaper while a window is maximised or full-screen; you can change that in Lively's *Performance* settings.

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
2. Under **Authentication → Advanced settings**, set **Allow public client flows** to **Yes**.
3. Under **API permissions → Add a permission → Microsoft Graph → Delegated**, add `Tasks.ReadWrite`, `User.Read`, `Mail.Read` and `Mail.Send`. The mail permissions power the Inbox tab and email notifications. If your tenant requires it, ask an admin to **Grant admin consent**.
4. Copy the **Application (client) ID** and **Directory (tenant) ID** into Settings → *Microsoft Planner*, then click **Sign in with Microsoft**. Open the link shown and enter the code.

Once you're signed in:

- **Pull.** Planner tasks assigned to you arrive in the **Basket**, with their plan, bucket, description, checklist, priority and due date. Each plan also appears as a list in the left rail.
- **Push.** Completing a Planner task, ticking its checklist, or changing its title, priority or due date writes the change back to Planner.
- **Schedule.** Sync runs every 15 minutes, or on demand with the **Planner** button.

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
