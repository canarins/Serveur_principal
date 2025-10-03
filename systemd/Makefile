DEST_DIR:=/etc/systemd/system
SERVICES:=apilog tcplogger telegram
SERVICES_FILES:=$(addprefix canarin-,$(addsuffix .service,$(SERVICES) ))

all: $(addprefix $(DEST_DIR)/,$(SERVICES_FILES))
$(addprefix $(DEST_DIR)/,$(SERVICES_FILES)): $(DEST_DIR)/%.service: %.service
	install -m 644 "$<" "$@"
