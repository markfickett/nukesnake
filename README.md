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