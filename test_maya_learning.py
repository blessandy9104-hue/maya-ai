import maya_chat

def main():
    result = maya_chat.maya_local_command('research philosophy')
    assert 'Brief research summary:' in result
    assert 'Evidence:' in result
    assert 'No trusted memory update occurred.' in result
    assert 'Philosophy' in result
    print('Maya unified research-learning boundary test passed')

if __name__ == '__main__':
    main()
