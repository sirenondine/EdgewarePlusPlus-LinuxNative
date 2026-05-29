Corruption.json
Corruption is a feature in Edgeware++ that will make the pack go though 'levels'  starting from 1. In most cases the pack will get lewder and more depraved going through the levels. Others may change the theme or change character, it all depends on the pack creator.
it's a pretty fun and neat feature, try it and have fun! -fishyfishe999

There are three main parts within corruption.json
moods , the moods settings for each corruption levels, you can either add or remove moods
wallpapers, you can set Wallpapers for each corruption levels
configs ,  the settings for each corruption levels

Example
{
"moods": {
  "1": {
    "add": ["mood1","mood2"],
    "remove": []
  },
  "2": {
    "add": ["mood3"],
    "remove": ["mood1"]
  },
  "3": {
    "add": [],
    "remove": ["mood2"]
  }
},
"wallpapers": {
  "1": "Wallpaper.png",
  "2": "Wallpaper2.png",
  "3": "Wallpaper3.png",
  "default": "Wallpaper.png"
},

"config": {
  "1": {
    "vidMod": 0,
    "notificationMood": 1, 
    "notificationChance": 1, 
    "notificationImageChance": 100
  },
  "2": {
    "vidMod": 0,
    "capPopChance": 5, 
    "capPopOpacity": 33, 
    "capPopTimer": 1000, 
    "capPopMood": 0, 
    "subliminalsAlpha": 20, 
    "messageOff": 0,
    "movingChance": 5, 
    "movingSpeed": 2, 
    "movingRandom": 1, 
    "notificationMood": 1, 
    "notificationChance": 1, 
    "notificationImageChance": 100
  },
  "3": {
    "vidMod": 10,
    "capPopChance": 20, 
    "capPopOpacity": 33, 
    "capPopTimer": 1000, 
    "capPopMood": 0, 
    "subliminalsAlpha": 20, 
    "messageOff": 0,
    "movingChance": 10, 
    "movingSpeed": 2, 
    "movingRandom": 1, 
    "notificationMood": 1, 
    "notificationChance": 3, 
    "notificationImageChance": 100
  }
}
}

Additional Notes
The Corruption levels must be named 1, 2, 3, 4, 5, ... and so on otherwise it won't be valid
 
Fishe (Comms 3/3)
 changed the post title: Corruption.json Explanation — 1/11/25, 7:46 AM
Fishe (Comms 3/3)
OP
 — 1/13/25, 6:05 AM
List of configs that does not work on corruption.json (Blacklisted configs)
        "version",  
        "versionplusplus"
        "panicButton"
        "safeword"
        "drivePath"
        "safeMode"
        "toggleInternet"
        "toggleHibSkip"
        "toggleMoodSet"
        "corruptionMode"
        "vlcMode"
        "presetsDanger"
        "corruptionDevMode"
        "corruptionFullPerm"
        "messageOff"
        "runOnSaveQuit"
        "themeNoConfig"
        "desktopIcons"
        "showLoadingFlair"
        "rotateWallpaper"
        "replace"
        "replaceThresh"
        "avoidList"
        "start_on_logon"
        "showDiscord"
        "timerMode"
        "timerSetupTime"
        "hibernateMode"
        "start_on_logon"
        "lkToggle"
        "mitosisMode"
