#!/usr/bin/env python

################################################################################
#                                                                              #
# Copyright (c) 2015 Cisco Systems                                             #
# All Rights Reserved.                                                         #
#                                                                              #
#    Licensed under the Apache License, Version 2.0 (the "License"); you may   #
#    not use this file except in compliance with the License. You may obtain   #
#    a copy of the License at                                                  #
#                                                                              #
#         http://www.apache.org/licenses/LICENSE-2.0                           #
#                                                                              #
#    Unless required by applicable law or agreed to in writing, software       #
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT #
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the  #
#    License for the specific language governing permissions and limitations   #
#    under the License.                                                        #
#                                                                              #
################################################################################
"""
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
"""

import sys
import acitoolkit.acitoolkit as aci
import warnings
import requests
import string
import json
import sys

################################################################################
# Functions using raw API (should be migrated to the aci toolkit for a
#   cleaner implementation)
# Not all functions are used, some cleanup wouldnt be bad
################################################################################

def apiclogin(apicurl, username, password):
    # Login (POST http://10.49.238.40/api/aaaLogin.xml)
    # Returns auth cookie
    try:
        r = requests.post(
                          url=apicurl+"/api/aaaLogin.xml",
                          data = '<aaaUser name=\"'+username+'\" pwd=\"'+password+'\" />')
        return r.cookies
    except requests.exceptions.RequestException as e:
        print('Login HTTP Request failed')

def create_fex_binding(apicurl, authcookie, tenant, anp, epg, leaf, fex, port, vlanid):
    # Create binding
    try:
        r = requests.post(
           url=apicurl+"/api/node/mo/uni/tn-"+tenant+"/ap-"+anp+"/epg-"+epg+".json",
           data = '{\"fvRsPathAtt\":{\"attributes\":{\"encap\":\"vlan-'+vlanid+'\",\"instrImedcy\":\"immediate\",\"tDn\":\"topology/pod-1/paths-'+leaf+'/extpaths-'+fex+'/pathep-[eth1/'+port+']\",\"status\":\"created\"},\"children\":[]}}',
           cookies = authcookie)
    except requests.exceptions.RequestException as e:
        print('Create FEX Binding Request failed')

def remove_fex_binding(apicurl, authcookie, tenant, anp, epg, leaf, fex, port, vlanid):
    try:
        r = requests.post(
           url=apicurl+"/api/node/mo/uni/tn-"+tenant+"/ap-"+anp+"/epg-"+epg+".json",
           data = '{\"fvAEPg\":{\"attributes\":{\"dn\":\"uni/tn-'+tenant+'/ap-'+anp+'/epg-'+epg+'\",\"status\":\"modified\"},\"children\":[{\"fvRsPathAtt\":{\"attributes\":{\"dn\":\"uni/tn-'+tenant+'/ap-'+anp+'/epg-'+epg+'/rspathAtt-[topology/pod-1/paths-'+leaf+'/extpaths-'+fex+'/pathep-[eth1/'+port+']]\",\"status\":\"deleted\",\"tDn\":\"topology/pod-1/paths-'+leaf+'/extpaths-'+fex+'/pathep-[eth1/'+port+']\"},\"children\":[]}}]}}',
           cookies = authcookie)
    except requests.exceptions.RequestException as e:
        print('Remove FEX Binding Request failed')

def create_binding_untagged(apicurl, authcookie, tenant, anp, epg, leaf, port, vlanid):
    try:
        r = requests.post(
           url=apicurl+"/api/node/mo/uni/tn-"+tenant+"/ap-"+anp+"/epg-"+epg+".json",
           data = '{\"fvRsPathAtt\":{\"attributes\":{\"encap\":\"vlan-'+vlanid+'\",\"instrImedcy\":\"immediate\",\"mode\":\"untagged\",\"tDn\":\"topology/pod-1/paths-'+leaf+'/pathep-[eth1/'+port+']\",\"status\":\"created\"},\"children\":[]}}',
           cookies = authcookie)
    except requests.exceptions.RequestException as e:
        print('Create binding request failed')

def remove_binding_untagged(apicurl, authcookie, tenant, anp, epg, leaf, port):
    try:
        r = requests.post(
           url=apicurl+"/api/node/mo/uni/tn-"+tenant+"/ap-"+anp+"/epg-"+epg+".json",
           data = '{\"fvAEPg\":{\"attributes\":{\"dn\":\"uni/tn-'+tenant+'/ap-'+anp+'/epg-'+epg+'\",\"status\":\"modified\"},\"children\":[{\"fvRsPathAtt\":{\"attributes\":{\"dn\":\"uni/tn-'+tenant+'/ap-'+anp+'/epg-'+epg+'/rspathAtt-[topology/pod-1/paths-'+leaf+'/pathep-[eth1/'+port+']]\",\"status\":\"deleted\",\"tDn\":\"topology/pod-1/paths-'+leaf+'/pathep-[eth1/'+port+']\"},\"children\":[]}}]}}',
           cookies = authcookie)
    except requests.exceptions.RequestException as e:
        print('Remove binding request failed')

def shutdown_port (apicurl, authcookie, leaf, fex, port):
    try:
        r = requests.post(
           url=apicurl+"/api/node/mo/uni/fabric/outofsvc.json",
           data = "{\"fabricRsOosPath\":{\"attributes\":{\"tDn\":\"topology/pod-1/paths-"+leaf+"/extpaths-"+fex+"/pathep-[eth1/"+port+"]\",\"lc\":\"blacklist\"},\"children\":[]}}",
           cookies = authcookie)
    except requests.exceptions.RequestException as e:
        print('Port shutdown Request failed')

################################################################################
# End of Functions using raw API
################################################################################

# Global variable with the name of the file where the MAC address table is stored
mac_list_file='mac_list.txt'

# This function should look somewhere (database, JSON file, etc) and returns
#    the EPG where a certain MAC should be configured on. If no entry is found
#    it will return 'None'
def get_mac_data(macaddress, mac_list):
    for mac_entry in mac_list:
        if (mac_entry["MAC"] == macaddress):
            return mac_entry
    return None

# Loads the MAC/EPG bindings into memory
def load_mac_list():
      try:
         with open(mac_list_file) as json_file:
            return json.load(json_file)
      except:
         print "Error loading data from %s" % filename

# Saves the MAC/EPG bindings to disk
def save_mac_list(mac_list):
     jsonstring = json.dumps(mac_list)
     try:
       configfile=open(mac_list_file, "w")
       configfile.write (jsonstring)
       configfile.close()
     except:
       print "Error writing to %s" % filename

# Dumps the mac_list to stdout
def print_mac_list (mac_list):
    for mac_entry in mac_list:
        print mac_entry

# Update the LastSeen field for a certain MAC
def update_lastseen (mac_list, macaddress, lastseen):
    temp = []
    for mac_entry in mac_list:
        if (mac_entry["MAC"] == macaddress):
            mac_entry['LastSeen'] = lastseen
        temp.append(mac_entry)
    return temp

def main():
    # Learning mode Enabled / Disabled
    # In learning mode all seen addresses are added into the database
    learning_mode = False

    # Array with addresses loaded from a file. Each element in the list is a dictionary
    #    with MAC, Tenant, ANP, EPG and VLAN
    mac_list = []

    # Default isolated EPG
    isolatedEPG = {"Tenant":"Quarantine", "ANP":"Quarantine_ANP", "EPG":"Quarantine_EPG", "VLANID":"3999"}

    # If not in learning mode, first thing to do is loading the list of authorized MAC addresses
    if not learning_mode:
        print "Initiating MAC Authorization routine in ACTIVE mode, the following MAC list has been loaded:"
        mac_list = load_mac_list ()
        print_mac_list (mac_list)
    else:
        print "Initiating MAC Authorization routine in LEARNING mode."

    # Take login credentials from the command line if provided
    # Otherwise, take them from your environment variables file ~/.profile
    description = ('Application that logs on to the APIC and tracks'
                   ' all of the Endpoints in a MySQL database.')
    creds = aci.Credentials(qualifier=('apic'), description=description)
    args = creds.get()

    # Login to APIC
    session = aci.Session(args.url, args.login, args.password)
    resp = session.login()
    if not resp.ok:
        print '%% Could not login to APIC'
        sys.exit(0)

    # Subscribe to End Point live updates
    aci.Endpoint.subscribe(session)
    while True:
        if aci.Endpoint.has_events(session):
            ep = aci.Endpoint.get_event(session)
            epg = ep.get_parent()
            app_profile = epg.get_parent()
            tenant = app_profile.get_parent()

            # EP leaves: remove static binding from EPG and put back in isolated EPG
            if ep.is_deleted():
                # Only take action if in non-learning mode. In learning mode there is nothing to learn
                if learning_mode:
                    print "Detected MAC address %s disconnected from interface %s on EPG %s - LEARNING MODE" % (ep.mac, ep.if_name, epg.name)
                else:
                    print "Detected MAC address %s disconnected from interface %s on EPG %s" % (ep.mac, ep.if_name, epg.name)
                    # First of all, find out whether this MAC address had been previously authorized
                    mac_info = get_mac_data(ep.mac, mac_list)
                    if mac_info == None:
                        print "MAC address %s disconnected, not in the authorized list: do nothing" % ep.mac
                    # If auth info was found, it means we need to put the port back in quarantine
                    else:
                        # Verify that the interface name is non-empty
                        if ep.if_name == None:
                            print "No valid interface provided by the EP-disconnect event, taking last seen interface %s" % mac_info['LastSeen']
                            ifname = mac_info['LastSeen']
                        else:
                            ifname=ep.if_name
                        # Compare the EPG where the EP is disconnected from with its authorized EPG. If they are not the same, do nothing
                        if epg.name == mac_info['EPG']:
                            # Identify port information
                            if_data = ifname.split("/")
                            if (len(if_data) == 5):
                                print "FEX ports not supported"
                            elif (len(if_data) == 4):
                                # Login to APIC
                                cookie = apiclogin (args.url, args.login, args.password)
                                # Remove static binding from EPG
                                remove_binding_untagged (args.url, cookie, tenant.name, app_profile.name, epg.name,if_data[1], if_data[3])
                                # Add static binding to isolated EPG
                                create_binding_untagged (args.url, cookie, isolatedEPG['Tenant'], isolatedEPG['ANP'], isolatedEPG['EPG'],if_data[1], if_data[3], isolatedEPG['VLANID'])
                                print "Authorized MAC address %s disconnected, port moved to EPG %s" % (ep.mac, isolatedEPG["EPG"])
                            else:
                                print "I dont understand the format of ep.if_name %s" % ep.if_name
                        else:
                            print "MAC address disconnected from EPG %s other than its home EPG %s: doing nothing" % (epg.name, mac_info['EPG'])

            # EP is connected: remove static binding from isolated EPG and put in target EPG
            else:
                #data = (ep.mac, ep.ip, tenant.name, app_profile.name, epg.name,
                #        ep.if_name, convert_timestamp_to_mysql(ep.timestamp))

                # In learning mode: add the learnt MAC to the list (and save it to file)
                if learning_mode:
                    # Check whether the list was in the list of VLANs already, if not, add it
                    mac_info = get_mac_data(ep.mac, mac_list)
                    if mac_info == None:
                        mac_list.append({"MAC":ep.mac, "Tenant":tenant.name, "ANP":app_profile.name, "EPG":epg.name, "VLANID":"", "LastSeen":ep.if_name})
                        print "Detected MAC address %s added to list of allowed MACs - LEARNING MODE" % ep.mac
                        save_mac_list(mac_list)
                    else:
                        print "MAC address %s already in the list of allowed MACs - LEARNING MODE" % ep.mac
                else:
                    print "Detected MAC address %s connected to interface %s on EPG %s" % (ep.mac, ep.if_name, epg.name)
                    # Verify whether EPG on that port is the isolated EPG, otherwise do not do anything
                    #   Now verifying only EPG name, should verify ANP and tenant too?
                    if (epg.name==isolatedEPG['EPG']):
                        # Verify that the interface name is non-empty
                        if ep.if_name == None:
                            print "No valid interface provided by the EP-connect event"
                        else:
                            # The interface string will have 4 fields in case of a leaf port, and 5 fields in case of a FEX port
                            if_data=ep.if_name.split("/")
                            if (len(if_data) == 5):
                                print "FEX ports not supported"
                            elif (len(if_data) == 4):
                                # Try to find information for that MAC address
                                mac_info = get_mac_data(ep.mac, mac_list)
                                # If no entry is found, do nothing (the MAC address is not in the list
                                if mac_info == None:
                                    print "Unauthorized MAC %s seen on port %s, left in quarantine" % (ep.mac, ep.if_name)
                                else:
                                    # Update LastSeen information
                                    mac_list = update_lastseen(mac_list, ep.mac, ep.if_name)
                                    save_mac_list(mac_list)
                                    # Remove binding from isolated EPG
                                    cookie = apiclogin (args.url, args.login, args.password)
                                    remove_binding_untagged (args.url, cookie, isolatedEPG['Tenant'], isolatedEPG['ANP'], isolatedEPG['EPG'],if_data[1], if_data[3])
                                    # Add static binding to new EPG
                                    create_binding_untagged (args.url, cookie, mac_info['Tenant'], mac_info['ANP'], mac_info['EPG'],if_data[1], if_data[3], mac_info['VLANID'])
                                    print "Authorized MAC address %s moved to EPG %s" % (ep.mac, mac_info["EPG"])
                            else:
                                print "I dont understand the format of ep.if_name %s" % ep.if_name

# Run the main routine if not loaded as module
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
