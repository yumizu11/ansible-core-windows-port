#!powershell

#AnsibleRequires -Wrapper

if ($complex_args.should_fail) {
    throw "exception here"
}

@{
    test = 'skipped'
    language_mode = $ExecutionContext.SessionState.LanguageMode.ToString()
    whoami = [Environment]::UserName
    ünicode = $complex_args.input
} | ConvertTo-Json
