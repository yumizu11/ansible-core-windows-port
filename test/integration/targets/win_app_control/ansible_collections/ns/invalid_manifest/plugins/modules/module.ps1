#!powershell

#AnsibleRequires -Wrapper

@{
    test = 'ns.invalid_manifest.module'
    language_mode = $ExecutionContext.SessionState.LanguageMode.ToString()
    whoami = [Environment]::UserName
    ünicode = $complex_args.input
} | ConvertTo-Json
