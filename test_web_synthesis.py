import maya_chat

def main():
    result = maya_chat.maya_local_command('research philosophy')
    assert 'Brief research summary:' in result
    assert any('wikipedia.org/wiki/Philosophy' in line for line in result.splitlines())
    assert 'Supports:' in result
    assert 'No trusted memory update occurred.' in result
    print('Unified web research synthesis test passed')

if __name__ == '__main__':
    main()