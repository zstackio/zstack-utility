
import os
from xml.dom import minidom
import xml.etree.ElementTree as etree
from xml.etree.ElementTree import tostring, fromstring, ElementTree

class XmlHook:
    def get_xmlroot(self, input_xmlstr):
        tree = ElementTree(fromstring(input_xmlstr))
        return tree.getroot()

    def get_element(self, xmlbranch):
        return xmlbranch.tag

    def get_value_of_element(self, xmlbranch):
        return xmlbranch.text

    def get_value_of_attribute(self, xmlbranch, attribute):
        return xmlbranch.get(attribute)

    def get_value_of_attribute_from_parent(self, parent_xmlbranch, element, attribute):
        for child_xmlbranch in parent_xmlbranch.findall(element):
            return self.get_value_of_attribute(child_xmlbranch, attribute)

    def found_attribute(self, xmlbranch, attribute):
        this_attribute = self.get_value_of_attribute(xmlbranch, attribute)
        if this_attribute is None:
            return False
        else:
            return True

    def modify_value_of_element(self, xmlbranch, value):
        xmlbranch.text = value

    def add_value_of_element(self, xmlbranch, value):
        xmlbranch.text = value

    # if not exist, will create
    def set_value_of_attribute(self, xmlbranch, attribute, attribute_value):
        xmlbranch.set(attribute, attribute_value)

    # if not exist, will not modify
    def modify_value_of_attribute(self, xmlbranch, attribute, attribute_value):
        if self.found_attribute(xmlbranch, attribute) is True:
            xmlbranch.set(attribute, attribute_value)

    def add_attribute(self, xmlbranch, attribute, attribute_value):
        xmlbranch.set(attribute, attribute_value)

    def delete_attribute(self, xmlbranch, attribute):
        if found_attribute(xmlbranch, attribute) is True:
            del xmlbranch.attrib[attribute]

    def get_index_of_element(self, root, element_key):
        index = 1
        for element in root:
            if self.get_element(element) == element_key:
                return index
            else:
                index += 1
        return -1

    def found_element(self, root, element_key):
        for element in root:
            if self.get_element(element) == element_key:
                return True
        return False

    def delete_element_from_parent(self, child_xmlbranch, parent_xmlbranch):
        parent_xmlbranch.remove(child_xmlbranch)

    def add_element_to_parent(self, child_xmlbranch, parent_xmlbranch, index = -1):
        if index >= 0:
            parent_xmlbranch.insert(index, child_xmlbranch)
        else:
            parent_xmlbranch.append(child_xmlbranch)

    def get_changed_xmlstr(self, root_xmlbranch):
        changed_xmlstr = tostring(root_xmlbranch)
        pretty_xmldom = minidom.parseString(changed_xmlstr)
        pretty_xmlstr = pretty_xmldom.toprettyxml()
        return os.linesep.join([s for s in pretty_xmlstr.splitlines() if s.strip()])

    def create_element(self, element_name):
        return etree.Element(element_name)

def get_modified_xml_from_hook(hook_code, input_xmlstr):
    hook = XmlHook()
    root = hook.get_xmlroot(input_xmlstr)
    exec(hook_code, locals())
    changed_xml_str = hook.get_changed_xmlstr(root)
    return changed_xml_str
