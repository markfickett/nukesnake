PRETTY_NAME = Nuke Snake

make pb2:
	protoc --python_out=. *.proto

mac_app: pb2
	rm -rf "out/$(PRETTY_NAME).app"
	mkdir -p out
	cp -r mac "out/$(PRETTY_NAME).app"
	cp *.py "out/$(PRETTY_NAME).app/Contents/Resources/"

mac_dmg: mac_app
	mkdir out/macdmg
	mv "out/$(PRETTY_NAME).app" out/macdmg
	hdiutil create "out/$(PRETTY_NAME).dmg" -volname "$(PRETTY_NAME)" -srcfolder out/macdmg


clean:
	rm -f *_pb2.py
	rm -rf out
