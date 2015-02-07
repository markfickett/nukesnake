mac_app: pb2
	rm -r NukeSnake.app
	cp -r mac NukeSnake.app
	cp *.py NukeSnake.app/Contents/Resources/

make pb2:
	protoc --python_out=. *.proto

clean:
	rm -f *_pb2.py
	rm -rf NukeSnake.app
