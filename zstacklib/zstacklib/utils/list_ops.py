def list_minus(list1, list2):
    '''
    @return: a list: the items from list1, except of the items in list2
    '''
    new_list = list(list1)
    for item in list2:
        if item in new_list:
            new_list.remove(item)
    return new_list

def unique_list(list1):
    '''
    @return: a list: only keep the unique obj from list1
    '''
    new_list = []
    for item in list1:
        if not item in new_list:
            new_list.append(item)

    return new_list

def list_and(list1, list2):
    '''
    Do and ops for 2 lists. 
    '''
    new_list = []
    for item in list1:
        if item in list2:
            new_list.append(item)

    return new_list
