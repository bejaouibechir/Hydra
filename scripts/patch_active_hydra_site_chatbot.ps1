$ErrorActionPreference = 'Stop'

$targetRoot = 'C:\Users\DELL\Desktop\hydra-site'
$sourceBundle = 'C:\Users\DELL\Desktop\Hydra\documentations\mockups\assets\hydra-chatbot-engine.js'
$pagePath = Join-Path $targetRoot 'src\pages\playground.astro'
$bodyPath = Join-Path $targetRoot 'src\_mock\playground.body.html'
$scriptPath = Join-Path $targetRoot 'src\_mock\playground.js'
$cssPath = Join-Path $targetRoot 'src\_mock\playground.css'
$publicAssets = Join-Path $targetRoot 'public\assets'
$bundlePath = Join-Path $publicAssets 'hydra-chatbot-engine.js'
$backupRoot = Join-Path $targetRoot 'src\_backups\chatbot-local-engine'

if (-not (Test-Path -LiteralPath $targetRoot)) { throw "Target project not found: $targetRoot" }
foreach ($path in @($pagePath, $bodyPath, $scriptPath, $cssPath, $sourceBundle)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}

New-Item -ItemType Directory -Force -Path $backupRoot, $publicAssets | Out-Null
foreach ($path in @($pagePath, $bodyPath, $scriptPath, $cssPath)) {
    $backup = Join-Path $backupRoot ([IO.Path]::GetFileName($path))
    if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $path -Destination $backup }
}
Copy-Item -LiteralPath $sourceBundle -Destination $bundlePath -Force

$page = Get-Content -LiteralPath $pagePath -Raw -Encoding UTF8
if ($page -notmatch 'hydra-chatbot-engine\.js') {
    $page = $page.Replace(
        '  <script is:inline set:html={js}></script>',
        "  <script is:inline src=`"/assets/hydra-chatbot-engine.js?v=20260804-5`"></script>`r`n  <script is:inline set:html={js}></script>"
    )
}
$page = [regex]::Replace($page, '/assets/hydra-chatbot-engine\.js(?:\?v=[^"'']+)?', '/assets/hydra-chatbot-engine.js?v=20260804-5')
Set-Content -LiteralPath $pagePath -Value $page -Encoding UTF8

$body = Get-Content -LiteralPath $bodyPath -Raw -Encoding UTF8
$body = $body.Replace(
    '<div class="chat-head"><span class="dot"></span><span id="chatTitle">Ask Hydra · powered by HydraLM</span><span style="margin-left:auto">simulated</span>',
    '<div class="chat-head"><span class="dot"></span><span id="chatTitle">Ask Hydra · DSL assistant</span><span style="margin-left:auto;color:var(--ok)">local</span>'
)
Set-Content -LiteralPath $bodyPath -Value $body -Encoding UTF8

$script = Get-Content -LiteralPath $scriptPath -Raw -Encoding UTF8
$oldPattern = '(?s)function botReply\(q\)\{q=q\.toLowerCase\(\);.*?return "Good question\. In the real product this is answered by HydraLM over the live DSL schema; this mock gives canned answers\.";\}'
$newFunction = @'
function currentChatOperation(){var steps=parseSteps($("fTransform").value);return steps.length?steps[0].op:undefined;}
function currentChatFiles(){return {"sources.yaml":$("fSources").value,"transformations.yaml":$("fTransform").value,"destinations.yaml":$("fDest").value,"pipeline.yaml":$("fPipeline").value};}
function botReply(q){
  if(!window.hydraChat)return {answer:"The local Hydra DSL engine is not ready. Reload the page once.",actions:[]};
  var msg=$("validationMsg"),errors=[];
  if(msg.classList.contains("err")&&msg.textContent)errors.push({message:msg.textContent,path:"transformations.yaml"});
  var response=window.hydraChat.answerHydraDsl({
    contractVersion:"1.0",requestId:"playground-"+Date.now(),locale:"en",question:q,assistanceLevel:"explanation",
    context:{hydraVersion:"1.2.0",dslVersion:"1.1",selectedOperation:currentChatOperation(),currentDsl:$("fTransform").value,currentFiles:currentChatFiles(),inputRows:(SRC_DATA[activeSrc]||SRC_DATA.orders).rows.slice(0,50),validationErrors:errors,executionMode:"local_simulation"}
  });
  return response;
}
'@
$updated = [regex]::Replace($script, $oldPattern, $newFunction, 1)
if ($updated -eq $script -and $script -match 'this mock gives canned answers') {
    throw 'Could not replace the simulated botReply function.'
}
$engineBlockPattern = '(?s)function currentChatOperation\(\).*?(?=function chatAdd\()'
$updated = [regex]::Replace($updated, $engineBlockPattern, $newFunction + "`r`n", 1)
$chatFunctionsPattern = '(?s)function chatAdd\(who,html\).*?(?=var CHAT_Q=)'
$chatFunctions = @'
function chatAdd(who,html){var d=document.createElement('div');d.className="msg "+who;
  d.innerHTML="<div class='av'>"+(who==='bot'?'Hy':'you')+"</div><div class='bub'>"+html+"</div>";
  $("chatMsgs").appendChild(d);$("chatMsgs").scrollTop=$("chatMsgs").scrollHeight;return d.querySelector(".bub");}
function chatAddResponse(response){
  var bubble=chatAdd('bot',esc(response.answer));
  if(response.actions&&response.actions.length){var resources=document.createElement("div");resources.className="chat-resources";
    var seen={};response.actions.slice(0,3).forEach(function(action){if(!action.href||seen[action.href])return;seen[action.href]=true;var link=document.createElement("a");link.href=action.href;link.textContent=action.label;resources.appendChild(link);});
    if(resources.children.length)bubble.appendChild(resources);}
}
function chatSend(q){q=(q||$("chatIn").value).trim();if(!q)return;chatAdd('user',esc(q));$("chatIn").value="";setTimeout(function(){try{chatAddResponse(botReply(q));}catch(error){console.error(error);chatAdd('bot',"I could not process that question locally.");}},120);}
'@
$updated = [regex]::Replace($updated, $chatFunctionsPattern, $chatFunctions + "`r`n", 1)
$updated = $updated.Replace(
    'chatAdd(''bot'',"Hi! Ask me anything about the Hydra DSL — sources, transformations, destinations.");',
    'chatAdd(''bot'',"Hi! I answer locally from the validated Hydra DSL corpus. No LLM or network request is used.");'
)
Set-Content -LiteralPath $scriptPath -Value $updated -Encoding UTF8

$css = Get-Content -LiteralPath $cssPath -Raw -Encoding UTF8
if ($css -notmatch '\.chat-resources') {
    $css += @'

.chat-resources{display:flex;flex-direction:column;gap:6px;margin-top:9px;padding-top:8px;border-top:1px solid var(--border)}
.chat-resources a{display:block;padding:6px 8px;border:1px solid var(--border);border-radius:7px;background:var(--bg-panel);color:var(--accent-text);font-size:11.5px;font-weight:600;text-decoration:none}
.chat-resources a:hover{border-color:var(--accent);background:var(--bg-soft)}
'@
    Set-Content -LiteralPath $cssPath -Value $css -Encoding UTF8
}

Write-Output "Patched active site: $targetRoot"
Write-Output "Backup: $backupRoot"
Write-Output "Bundle: $bundlePath"
