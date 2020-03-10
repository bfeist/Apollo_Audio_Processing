EKG_DATA=ekg_data.json
RENDERING_DIR=render-js
MOVIE=a13_t708_ch13_ekg_032h37m00s950.mp4

EKG=$(RENDERING_DIR)/$(EKG_DATA)

all: $(MOVIE)

DA13_T911_HR2U_CH13.wav:
	echo "You need a defluttered copy of channel 13 from tape"
	echo "T911."
	echo "STOP"
	
$(EKG): DA13_T911_HR2U_CH13.wav
	#
	# Skip to 55m:11s and retrieve 4m:3s of data
	#
	echo "var data =" > $@
	python a13_t911_ekg_telemetry.py -s 3311 -d 247 $^ 50 >> $@
	echo ";" >> $@

input.webm: $(EKG)
	echo "You need input.webm. Currently manual process. Load"
	echo "render-js/index.html in Chrome, open up console"
	echo "execute run_animation();. Save downloaded file as"
	echo "input.webm"

trimmed.wav: DA13_T911_HR2U_CH13.wav
	sox $^ $@ trim 3310.68 247

$(MOVIE): input.webm trimmed.wav
	ffmpeg -i input.webm -i trimmed.wav -map 0:v:0 -map 1:a:0 \
		-c:a aac -b:a 64k $@
