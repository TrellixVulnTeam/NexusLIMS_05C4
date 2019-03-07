#! /usr/bin/env python
import xml.etree.ElementTree as ET
import os

#Takes XML generated by writeCalEvents.py and breaks
#each reservation into an individual XML record structured
#according to the Summary element of the schema

tree = ET.parse('cal_events.xml')
root = tree.getroot()

for element in root:
    #print(element)
    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        top = ET.Element("nx:Summary")
        content = entry.find('{http://www.w3.org/2005/Atom}content')
        
        for properties in content:
            #For the title of the Instrument reservation
            #title = ET.SubElement(top, "title")
            #title_extr="N/A"
            #title.text=title_extr
            
            #Call an ID Generating Script Here
            #idd = ET.SubElement(exp, "id")
            #id_extr= "ark:/88434/nxp0"
            #idd.text = id_extr
            
            experimenter_tag = properties.find('{http://schemas.microsoft.com/ado/2007/08/dataservices}Title')
            experimenter= ET.SubElement(top, "experimenter")
            experimenter_extr = experimenter_tag.text
            experimenter.text=experimenter_extr
            
            #Insert Collab Extract Script Here
            collaborator=ET.SubElement(top, "collaborator")
            #collaborator.text=collab_extr
            #collab_extr="Vidanoy"
            

            #Modify so requests script knows it's a Titan list
            instrument=ET.SubElement(top, "instrument")
            instr_extr="Titan"
            instrument.text=instr_extr
            
            reservationStart=ET.SubElement(top, "reservationStart")
            resStart_tag = properties.find('{http://schemas.microsoft.com/ado/2007/08/dataservices}StartTime')
            resStart_extr=resStart_tag.text
            reservationStart.text=resStart_extr            
            
            reservationEnd=ET.SubElement(top, "reservationEnd")
            resEnd_tag = properties.find('{http://schemas.microsoft.com/ado/2007/08/dataservices}EndTime')
            resEnd_extr=resEnd_tag.text
            reservationEnd.text=resEnd_extr
            
            motivation=ET.SubElement(top, "motivation")
            motivation_tag = properties.find('{http://schemas.microsoft.com/ado/2007/08/dataservices}Description')
            motiv_extr= motivation_tag.text
            motivation.text=motiv_extr
            
            tree=ET.ElementTree(top)
            
            filename=resStart_extr
            clean_filename = filename.replace(":", "_")
            path="files_generated"
            if not os.path.exists(path):
                os.mkdir(path)
            
            #Saves an XML for each reservation in a folder under the naming convention:
            #"Titan_Experimenter_ReservationStartDate.xml"
            tree.write(path+'/'+"Titan"+ "_"+ "%s"%(experimenter_extr) + "_"+ "%s"%(clean_filename) +".xml")