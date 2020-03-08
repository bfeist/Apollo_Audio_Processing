EKG_DATA=ekg_data.json
RENDERING_DIR=render-js

EKG=$(RENDERING_DIR)/$(EKG_DATA)

all: $(EKG)

DA13_T911_HR2U_CH13.wav:
	echo "You need a defluttered copy of channel 13 from tape"
	echo "T911."
	echo "STOP"
	
$(EKG): DA13_T911_HR2U_CH13.wav
	#
	# Skip to 55m:11s and retrieve 4m:3s of data
	#
	echo "var data =" > $@
	python a13_t911_ekg_telemetry.py -s 3311 -d 243 $^ 50 >> $@
	echo ";" >> $@
