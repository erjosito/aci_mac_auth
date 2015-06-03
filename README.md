Jose Moreno, josemor@cisco.com, aci-automac v0.2, June 2015

Simple application that logs on to the APIC and monitors EP attach/dettach
events. It will compare the MAC address of the EP being connected with a
predefined list of authorized MAC addresses.

If the EP is attached to a predefined Isolated EPG, and the MAC address is
in the authorized MAC address table, the EP will be moved to the EPG specified
by the entry in the MAC address table.
When that authorized EP disconnects from ACI, the port will be moved back to
the isolated EPG.

If the EP's MAC address is not found in the MAC address table, it is assumed
to be a non-authorized EP, and therefore left in the Isolated EPG.

The script has a learning_mode variable. If learning mode is active, it will generate
a sample MAC address table with all the EP attachments it sees, without changing
anything in the network.

This is more of a demo version, where the MAC address table is stored in a file
in JSON format.
