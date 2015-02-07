PRETTY_NAME = Nuke Snake
RESOURCES = out/$(PRETTY_NAME).app/Contents/Resources/
PROTO_DYLIB = libprotobuf.9.dylib

make pb2:
	protoc --python_out=. *.proto

out/google/protobuf/__init__.py:
	mkdir -p out
	cp /Library/Python/2.7/site-packages/protobuf-2.6.*.egg out/egg
	cd out && unzip egg

mac_app: pb2 out/google/protobuf/__init__.py /usr/local/lib/$(PROTO_DYLIB)
	rm -rf "out/$(PRETTY_NAME).app"
	mkdir -p out
	cp -r mac "out/$(PRETTY_NAME).app"
	cp LICENSE.txt "$(RESOURCES)"
	cp *.py "$(RESOURCES)"
	cp -r out/google "$(RESOURCES)"
	cp /usr/local/lib/$(PROTO_DYLIB) "$(RESOURCES)"
	install_name_tool -id "./$(PROTO_DYLIB)" "$(RESOURCES)$(PROTO_DYLIB)"
	install_name_tool -change /usr/local/lib/$(PROTO_DYLIB) "./$(PROTO_DYLIB)" "$(RESOURCES)google/protobuf/pyext/_message.so"

mac_dmg: mac_app
	mkdir -p out/macdmg
	mv "out/$(PRETTY_NAME).app" out/macdmg
	cp LICENSE.txt out/macdmg
	hdiutil create "out/$(PRETTY_NAME).dmg" -volname "$(PRETTY_NAME)" -srcfolder out/macdmg


clean:
	rm -f *_pb2.py
	rm -rf out
