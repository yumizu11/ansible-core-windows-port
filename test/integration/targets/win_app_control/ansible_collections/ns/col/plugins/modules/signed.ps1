#!powershell

#AnsibleRequires -Wrapper

@{
    test = 'signed'
    language_mode = $ExecutionContext.SessionState.LanguageMode.ToString()
    whoami = [Environment]::UserName
    ünicode = $complex_args.input
} | ConvertTo-Json
