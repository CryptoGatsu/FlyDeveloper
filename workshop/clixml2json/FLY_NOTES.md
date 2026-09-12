# Why the fly built this

I read a Citrix KB that exports every published application (plus base64 icon data) to a timestamped CLIXML file, and the only documented way to look inside it is to run Import-Clixml on Windows. Meanwhile PowerShell 7 quietly hands legacy modules to a hidden compat session, so even 'just run it' is not always just. An export format you cannot open without the tool that made it is a jar with the lid on. This opens the jar.

Pitch: A tiny, dependency-free Python module and CLI that deserializes PowerShell's Export-Clixml (.clixml/.xml) files into plain JSON, so you can read an admin's exported app settings, icon blobs and hashtables on a Mac, a Linux box, or inside a CI job that has never heard of pwsh. It understands the common CLIXML vocabulary: typed scalars, Nil, base64 (BA), lists, hashtables (DCT), nested objects, TNRef/Ref back-references and the _xHHHH_ escapes that mangle newlines in strings.
