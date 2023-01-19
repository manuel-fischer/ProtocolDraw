SVG_FILES = \
	rendered/communication.svg \
	rendered/actions.svg \
	rendered/font_style.svg \
	rendered/layout.svg \
	rendered/properties.svg \

all: $(SVG_FILES)


rendered/%.svg: examples/%.txt
	python3 ./draw_protocol.py $< -o $@