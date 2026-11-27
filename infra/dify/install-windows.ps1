param([ValidateSet("prepare","check","start")][string]$Action="prepare")
& py -3.13 "$PSScriptRoot/../../scripts/install_stand.py" $Action
exit $LASTEXITCODE
