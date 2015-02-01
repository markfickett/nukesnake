Overview
--------

![screenshot](https://farm8.staticflickr.com/7358/16418236931_283c410cb8_o.png)

[screenshot hosted on flickr](https://flic.kr/p/r1PKQx)

Inspired by [David Riggle's 1990 Mac game of the same name](http://macintoshgarden.org/games/nuke-snake), this is like Snake but you can shoot at your opponent, collect power-ups, and destroy the terrain or blow up mines. It is network multiplayer, with optional AI opponents.

Quick Start
-----------

    # Install Google protobuf libraries. Prompts for sudo.
    ./setup.sh
    # Generate the Python protos.
    protoc --python_out=. *.proto
    # Start the server.
    ./network.py --width 100 --height 30
    # Start any number of clients (optionally with AIs to play against).
    ./client.py --ai Terminator

License
-------

[Creative Commons Attribution NonCommercial ShareAlike 4.0](http://creativecommons.org/licenses/by-nc-sa/4.0/) Attribute to Mark Fickett and link to markfickett.com or github.com/markfickett/nukesnake .
