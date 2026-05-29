Tabs Overview
At the top of the config window are several tabs to help you navigate through Edgeware++ settings. Some of them contain "sub-tabs" to help further categorize settings. The main tabs are as follows:

General - Meta settings centered around managing Edgeware++ as a program, and viewing current pack information.
Annoyance/Runtime - Settings that are visible while Edgeware++ is running, such as popup frequency, etc.
Modes - Large-scale settings that drastically change how Edgeware++ works.
Corruption - An even larger scale change-over-time mode that is detailed enough to warrant its own tab!
Troubleshooting - Settings based around compatibility or legacy features.
Tutorial - The tutorial where much of this cheat sheet is sourced from.

General
Here are some very important setting that warrant talking about:

"Warn if Dangerous Settings Active" is a very important safety feature for new users, so much so that it's on by default! There are a few settings inside Edgeware++ that can negatively affect the user if turned on while unaware, so this setting alerts you before you save them. You can see a full list of what is considered dangerous by hovering over this warning setting, but most of them are confined to the sub-tab called Dangerous!
"Show Loading Flair" spawns a short "introductory" image whenever Edgeware++ is launched. Packs can sometimes have custom ones.
"Panic Hotkey" can be set to closes all popups and force-ends Edgeware++! Setting up a hotkey to do this for you at any time is extremely useful, so make sure you put it on something you won't forget! If the hotkey here doesn't work, you can check out a legacy setting in the Troubleshooting tab!
Annoyance
The "Annoyance" tab, which refers to the fact that most of the "annoying" popup settings can be found here!

There's two main sections we're going to look at: Popup Types and Popup Tweaks. Popup types is essentially the sub-tab where you decide what types of files appear when you run Edgeware++. Most of them have pretty in-depth help text, so I'll only briefly go over them here:

Popup Timer Delay: This is the core of how Edgeware++ works - when the elapsed time set here is met, a new popup is spawned.
Image Popups: Self explanatory! This is the main type of popup in Edgeware++.
Audio Popups: Audio that plays without any visual component.
Video Popups: Video, usually .mp4 files, that can play in full motion. Otherwise identical to image popups!
Website Popups: Opens your web browser to display a webpage!
Prompt Popups: Makes you type in a prompt before you can close it!
Subliminal Popups: Full-screen sized text that is meant to briefly flash before disappearing!
Notification Popups: Popups that display in your "notifications" section of your OS. Can include images as well!
Modes
Lowkey: Forces popups to spawn in the corner of your screen, rather than randomly all over. Best used with popup timeout or high delay as popups will stack on top of eachother.
Mitosis: When a popup is closed, more popups will spawn in its place depending on the mitosis strength.
Hibernate: Runs Edgeware++ covertly, without any popups. Instead, edgeware will be activated in short bursts. 
Hibernation Type: (see below)
Minimum/Maximum Sleep Duration: determine the range of the payload timer- hibernate mode will activate sometime between these two values.
Awaken Activity: determines the intensity of the hibernate mode payload, essentially the amount of popups spawned when it triggers.
Max Activity Length: how long the payload lasts, if using a hibernate type that has a duration.
Hibernation Types
Original: The original hibernate type that came with base Edgeware. Spawns a barrage of popups instantly, the max possible amount is based on your awaken activity.
Spaced: Essentially runs Edgeware normally, but activity spaced out equally over the activity length.
Glitch: Creates popups at random-ish intervals over a period of time. The total amount of popups spawned is based on the awaken activity. Perfect for those who want a 'virus-like' experience, or just something different every time.
Ramp: Similar to spaced, only the popup frequency gets faster and faster over the hibernate length.
Pump-Scare: When hibernate is triggered a popup with audio will appear for around a second or two, then immediately disappear.
Chaos: Every time hibernate activates, it randomly selects any of the other hibernate modes.
Corruption
Corruption is a highly specialized mode that packs have to explicitly support. When corruption is enabled, it will turn off and on moods based on a trigger set down below. For example, a pack might start off with only vanilla moods but get more fetish-oriented every 10 popups opened.

Full Permissions Mode: Allows packs to change Edgeware++ settings on top of also changing moods. While this allows for very unique packs with lots of changes, this can also be potentially dangerous. Only turn it on for packs you trust!
Triggers: Triggers are the goals that define how corruption changes over time. Whenever the selected condition is reached, they tell Edgeware++ to advance to the next "corruption level". See trigger types below.
Don't Cycle Wallpaper: Prevents the wallpaper from cycling as you go through corruption levels, instead defaulting to a pack defined static one.
Don't Cycle Theme: Prevents the theme from cycling as you go through corruption levels, instead staying as the theme you set in the "General" tab of the config window.
Purity Mode: Starts corruption mode at the highest corruption level, then works backwards to level 1. Retains all of your other settings for this mode, if applicable.
Corruption Dev View: Enables captions on popups that show various info as well as extra logs in debug.py.

Trigger Types
Timed: Transitions based on time elapsed in current session.
Popup: Transitions based on number of popups in current session.
Launch: Transitions based on number of Edgeware launches.
Script: Transitions handled by pack scripts. Needs to be setup by pack.
