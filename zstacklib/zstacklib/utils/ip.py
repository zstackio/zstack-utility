'''

@author: yyk
'''

class IpAddress(object):
    '''
    Help to save and compare IP Address. 
    '''
    def __init__(self, ip):
        self.ip_list = ip.split('.', 3)
        self.ips = []
        for item in self.ip_list:
            if not item.isdigit():
                raise Exception('%s is not digital' % item)
            if int(item) > 255 or item < 0:
                raise Exception('%s must be >=0 and <=255' % item)
            self.ips.append(int(item))

    def __cmp__(self, ip2):
        index = 0
        while index < 4:
            cmp_ret = cmp(self.ips[index], ip2.ips[index])
            if cmp_ret > 0:
                return 1
            elif cmp_ret < 0:
                return -1
            index += 1
        else:
            return 0

    def __gt__(self, ip2):
        if self.__cmp__(ip2) > 0:
            return True
        return False

    def __lt__(self, ip2):
        if self.__cmp__(ip2) < 0:
            return True
        return False

    def __eq__(self, ip2):
        if self.__cmp__(ip2) == 0:
            return True
        return False

    def __le__(self, ip2):
        if self.__cmp__(ip2) > 0:
            return False
        return True

    def __ge__(self, ip2):
        if self.__cmp__(ip2) < 0:
            return False
        return True

    def __str__(self):
        return '.'.join(self.ip_list)

    def __repr__(self):
        return self.__str__()
