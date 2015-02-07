PRETTY_NAME = Nuke Snake

make pb2:
	protoc --python_out=. *.proto

out/google/protobuf/__init__.py:
	mkdir -p out
	cp /Library/Python/2.7/site-packages/protobuf-2.6.*.egg out/egg
	cd out && unzip egg

mac_app: pb2 out/google/protobuf/__init__.py
	rm -rf "out/$(PRETTY_NAME).app"
	mkdir -p out
	cp -r mac "out/$(PRETTY_NAME).app"
	cp *.py "out/$(PRETTY_NAME).app/Contents/Resources/"
	cp LICENSE.txt "out/$(PRETTY_NAME).app/Contents/Resources/"
	cp -r out/google "out/$(PRETTY_NAME).app/Contents/Resources/"

mac_dmg: mac_app
	mkdir -p out/macdmg
	mv "out/$(PRETTY_NAME).app" out/macdmg
	cp LICENSE.txt out/macdmg
	hdiutil create "out/$(PRETTY_NAME).dmg" -volname "$(PRETTY_NAME)" -srcfolder out/macdmg


clean:
	rm -f *_pb2.py
	rm -rf out
