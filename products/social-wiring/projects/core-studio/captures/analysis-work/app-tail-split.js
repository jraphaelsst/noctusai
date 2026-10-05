ders.get("content-type");
if(!(t!=null&&t.startsWith(Gs)))throw new Error(`Expected content-type to be ${Gs}, Actual: ${t}`)}document.addEventListener("alpine:init",()=>{Alpine.data("aiChat",()=>({isOpen:!1,isLoading:!1,messages:[],newMessage:"",status:"Online",workspace_id:null,user_id:null,app_env:null,renderedMessageIds:new Set,eventSource:null,isThinking:!1,echo:null,isRecording:!1,audioBlob:null,audioUrl:null,selectedFile:null,showAudioArea:!1,showMicrophone:!0,showSendText:!1,showInputMessage:!0,
openFileInput(){this.$refs.fileInput.click()},handleFileSelect(e){const t=e.target.files[0];
if(t){const r=["application/pdf","text/plain","application/msword","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/vnd.oasis.opendocument.text","application/rtf"],i=[".pdf",".txt",".doc",".docx",".odt",".rtf"];
if(!r.includes(t.type)&&!i.some(s=>t.name.toLowerCase().endsWith(s))){alert("Tipo de arquivo não permitido. Por favor, selecione apenas arquivos PDF, TXT, DOC, DOCX, ODT ou RTF."),this.removeFile();
return}this.selectedFile=t}},
removeFile(){this.selectedFile=null,this.$refs.fileInput.value=""},get shouldShowMicrophone(){return this.showMicrophone&&!this.newMessage.trim()&&!this.showAudioArea},get shouldShowSendText(){return this.showSendText&&this.newMessage.trim()&&!this.showAudioArea},get shouldShowInputMessage(){return this.showInputMessage&&!this.showAudioArea},
switchToAudio(){this.showAudioArea=!0,this.showMicrophone=!1,this.showSendText=!1,this.showInputMessage=!1,this.newMessage="",setTimeout(()=>{$("#record-button-chat").click()},100)},
switchToText(){this.showAudioArea=!1,this.showMicrophone=!0,this.showSendText=!1,this.showInputMessage=!0,this.newMessage=""},
resetControls(){this.showAudioArea=!1,this.showMicrophone=!0,this.showSendText=!1,this.showInputMessage=!0,this.audioUrl=null,this.audioBlob=null},async init(){var e,t,r;
if(this.workspace_id=((e=document.querySelector('meta[name="workspace-id"]'))==null?void 0:e.content)||3,this.user_id=(t=document.querySelector('meta[name="user-id"]'))==null?void 0:t.content,this.app_env=((r=document.querySelector('meta[name="app-env"]'))==null?void 0:r.content)||"local",!this.user_id){console.error("user_id não encontrado");
return}await this.loadHistory(),this.scrollToBottom(),this.$watch("newMessage",i=>{i.trim()?(this.showSendText=!0,this.showMicrophone=!1):this.showAudioArea||(this.showSendText=!1,this.showMicrophone=!0)})},
onInputFocus(){!this.newMessage.trim()&&!this.showAudioArea&&(this.showMicrophone=!0,this.showSendText=!1)},
onInputBlur(){!this.newMessage.trim()&&!this.showAudioArea&&(this.showMicrophone=!0,this.showSendText=!1)},
toggleChat(){this.isOpen=!this.isOpen,this.isOpen&&!this.echo?(this.initPusher(),this.scrollToBottom()):!this.isOpen&&this.echo&&this.disconnectPusher()},
disconnectPusher(){this.echo&&(this.echo.disconnect(),this.echo=null)},
initPusher(){this.echo=new Echo({broadcaster:"pusher",key:"75830eeb9f5ab6e769a8",cluster:"us2",forceTLS:!0,enabledTransports:["ws","wss"],disableStats:!0,encrypted:!0,wsHost:"ws-us2.pusher.com",wsPort:443,wssPort:443,authEndpoint:"/broadcasting/auth",auth:{headers:{"X-CSRF-TOKEN":document.querySelector('meta[name="csrf-token"]').content}}}),this.echo.connector.pusher.connection.bind("connected",()=>{}),this.echo.connector.pusher.connection.bind("error",r=>{});
const e=`chat.${this.app_env}.user.${this.user_id}`,t=this.echo.private(e);
t.subscribed(()=>{}),t.error(r=>{console.error("Erro no canal:",r)}),t.listen(".nova-mensagem",r=>{try{const i=c=>{if(!c)return null;
if(typeof c=="string")return c;
if(c.assistant_message)return c.assistant_message;
if(c.response)return c.response;
if(c.result&&c.result.response)return c.result.response;
if(c.mensagem&&c.mensagem.mensagem){const l=i(c.mensagem.mensagem);
if(l)return l}if(Array.isArray(c))for(const l of c){const d=i(l);
if(d)return d}if(typeof c=="object")for(const l in c){const d=i(c[l]);
if(d)return d}return null},s=i(r),a=this.parseFileJsonMessage(s);
if(a){this.messages.push({id:Date.now()+"-user-file",type:"user",content:`
                                    <div class="d-flex align-items-center bg-black-50 p-2 rounded-3 mb-1">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" class="icon icon-tabler icons-tabler-filled icon-tabler-file me-2">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                            <path d="M12 2l.117 .007a1 1 0 0 1 .876 .876l.007 .117v4l.005 .15a2 2 0 0 0 1.838 1.844l.157 .006h4l.117 .007a1 1 0 0 1 .876 .876l.007 .117v9a3 3 0 0 1 -2.824 2.995l-.176 .005h-10a3 3 0 0 1 -2.995 -2.824l-.005 -.176v-14a3 3 0 0 1 2.824 -2.995l.176 -.005h5z" />
                                            <path d="M19 7h-4l-.001 -4.001z" />
                                        </svg>
                                        <span>${a.name}</span>
                                    </div>
                                `,formatted:!0,isHtml:!0}),this.scrollToBottom();
return}s?(this.isThinking=!1,this.messages.push({id:Date.now()+"-assistant",type:"assistant",content:s,time:this.formatTime(new Date),formatted:!0}),this.scrollToBottom()):console.warn("Nenhuma mensagem encontrada na estrutura:",r)}catch(i){console.error("Erro ao processar mensagem:",i),console.error("Dados que causaram o erro:",r)}}),console.log("Canais inscritos:",this.echo.connector.pusher.channels.all())},async sendAudioMessage(){var e,t;
console.log("sendAudioMessage chamado"),console.log("chatRecording:",window.chatRecording),console.log("chatRecording.audioBlob:",(e=window.chatRecording)==null?void 0:e.audioBlob),(t=window.chatRecording)!=null&&t.audioBlob?(console.log("Copiando audioBlob para Alpine"),this.audioBlob=window.chatRecording.audioBlob,this.audioUrl=URL.createObjectURL(this.audioBlob),console.log("Audio Blob definido no Alpine:",!!this.audioBlob),console.log("Audio URL definido no Alpine:",!!this.audioUrl),await this.sendMessage()):console.log("Nenhum áudio encontrado para enviar")},async sendMessage(){if(console.log("sendMessage chamado"),console.log("audioBlob presente:",!!this.audioBlob),console.log("audioUrl presente:",!!this.audioUrl),console.log("selectedFile presente:",!!this.selectedFile),this.audioBlob){console.log("Iniciando envio de áudio"),this.isLoading=!0,this.isThinking=!0;
const e=new FormData;
e.append("audio",this.audioBlob,"audio.webm"),e.append("workspace_id",this.workspace_id),e.append("user_id",this.user_id),e.append("app_env",this.app_env);
try{const t=await fetch("/api/return/integration/ai/chat",{method:"POST",headers:{"X-CSRF-TOKEN":document.querySelector('meta[name="csrf-token"]').content},body:e}),r=await t.json();
if(!t.ok)throw new Error(r.message||"Desculpe, ocorreu um erro 😔");
if(this.messages.push({id:Date.now()+"-user",type:"user",content:'<audio src="'+this.audioUrl+'" controls></audio>',time:this.formatTime(new Date)}),this.resetControls(),setTimeout(()=>{this.scrollToBottom()},100),window.chatRecording={isRecording:!1,timer:null,seconds:0,mediaRecorder:null,audioChunks:[],audioBlob:null,audioContext:null,analyser:null,dataArray:null},r.task_id)this.isThinking=!0;
else throw new Error("ID de processamento não recebido")}catch(t){console.error("Erro:",t),this.isThinking=!1,this.messages.push({id:Date.now()+"-error",type:"error",content:"Desculpe, ocorreu um erro ao enviar o áudio: "+t.message,time:this.formatTime(new Date),formatted:!1})}finally{this.isLoading=!1}}else if(this.newMessage.trim()||this.selectedFile){this.isLoading=!0,this.isThinking=!0;
const e=new FormData;
this.newMessage.trim()&&e.append("message",this.newMessage),this.selectedFile&&e.append("file",this.selectedFile),e.append("workspace_id",this.workspace_id),e.append("user_id",this.user_id),e.append("app_env",this.app_env);
try{const t=await fetch("/api/return/integration/ai/chat",{method:"POST",headers:{"X-CSRF-TOKEN":document.querySelector('meta[name="csrf-token"]').content},body:e}),r=await t.json();
if(!t.ok)throw new Error(r.message||"Desculpe, ocorreu um erro 😔");
if(this.selectedFile?(this.messages.push({id:Date.now()+"-user-file",type:"user",content:`
                                <div class="d-flex align-items-center bg-black-50 p-2 rounded-3 mb-1">
                                    <svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-file"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 2l.117 .007a1 1 0 0 1 .876 .876l.007 .117v4l.005 .15a2 2 0 0 0 1.838 1.844l.157 .006h4l.117 .007a1 1 0 0 1 .876 .876l.007 .117v9a3 3 0 0 1 -2.824 2.995l-.176 .005h-10a3 3 0 0 1 -2.995 -2.824l-.005 -.176v-14a3 3 0 0 1 2.824 -2.995l.176 -.005h5z" /><path d="M19 7h-4l-.001 -4.001z" /></svg>
                                    <span>${this.selectedFile.name}</span>
                                </div>
                            `,formatted:!0,isHtml:!0}),this.newMessage.trim()&&this.messages.push({id:Date.now()+"-user-message",type:"user",content:this.newMessage,time:this.formatTime(new Date),formatted:!1})):this.audioBlob?this.messages.push({id:Date.now()+"-user-audio",type:"user",content:'<audio src="'+this.audioUrl+'" controls></audio>',time:this.formatTime(new Date),formatted:!1}):this.messages.push({id:Date.now()+"-user",type:"user",content:this.newMessage,time:this.formatTime(new Date),formatted:!1}),this.newMessage="",this.selectedFile=null,this.scrollToBottom(),r.task_id)this.isThinking=!0;
else throw new Error("ID de processamento não recebido")}catch(t){console.error("Erro:",t),this.isThinking=!1,this.messages.push({id:Date.now()+"-error",type:"error",content:t.message,time:this.formatTime(new Date),formatted:!1})}finally{this.isLoading=!1}}},async pollJobStatus(e){let i=0;
const s=async()=>{try{const c=await(await fetch(`dashboard/user/ai/status/${e}`)).json();
if(c.error)throw new Error(c.error);
if(this.status=`${c.status_message||"Processando..."} (${c.progress}%)`,c.status==="completed"){if(!c.response)throw new Error("Resposta vazia recebida do servidor");
this.messages.push({id:this.messages.length+1,type:"assistant",content:c.response,time:this.formatTime(new Date),formatted:!0}),this.isLoading=!1,this.status="Online",this.scrollToBottom();
return}else{if(c.status==="error")throw new Error(c.error||"Erro durante o processamento");
if(i>=180)throw new Error("Tempo limite excedido")}i++,setTimeout(s,1e3)}catch(a){console.error("Erro no polling:",a),this.handleError(a.message)}};
s()},handleError(e){this.messages.push({id:this.messages.length+1,type:"assistant",content:`Desculpe, ocorreu um erro: ${e}`,time:this.formatTime(new Date),formatted:!1}),this.isLoading=!1,this.status="Online",this.scrollToBottom()},
scrollToBottom(){this.$nextTick(()=>{const e=this.$refs.messageContainer;
e.scrollTop=e.scrollHeight})},formatTime(e){return e.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})},parseFileJsonMessage(e){if(typeof e=="string"&&e.startsWith("{")&&e.endsWith("}"))try{const t=JSON.parse(e.replace(/(\w+):/g,'"$1":'));
if(t!=null&&t.name&&(t!=null&&t.id))return t}catch(t){console.error("Erro ao parsear JSON:",t)}return null},
cancelAudioRecording(){this.switchToText(),$(".div-controls-chat").addClass("hidden"),$(".div-audio-chat").removeClass("hidden"),$("#record-timer-chat").text("00:00"),$("#audio-player-chat").attr("src",""),window.chatRecording={isRecording:!1,timer:null,seconds:0,mediaRecorder:null,audioChunks:[],audioBlob:null,audioContext:null,analyser:null,dataArray:null}}}))});
function Xp(){if(!(typeof marked>"u"))try{const e=function({href:t,title:r,tokens:i}){const s=this.parser?this.parser.parseInline(i):i??"",a=r?` title="${r}"`:"";
return`<a href="${t}"${a} target="_blank" rel="noopener noreferrer">${s}</a>`};
if(typeof marked.use=="function")marked.use({renderer:{link:e}});
else if(typeof marked.setOptions=="function"){const t=new marked.Renderer;
t.link=e,marked.setOptions({renderer:t})}}catch(e){console.warn("[chat] marked config failed:",e)}}Xp();
function Qp(e,t,r,i,s,a,c){return{steps:[],stepsOpen:!0,typingText:"",typingTimer:null,streaming:!1,streamedText:"",typingHtml:"",renderTimer:null,streamId:0,activeAbortController:null,localMessages:[],localConversationId:null,hasSentMessage:!1,traceVisible:!1,sidebarConversations:[],_streamUrl:r||"",_docUploadUrl:i||"",_creditsUrl:s||"",_rechargesUrl:a||"",_faturamentoUrl:c||"",_actionAgentMap:{},rechargeVisible:!1,rechargeLoading:!1,rechargeHasCard:!0,rechargePackages:[],rechargeSelectedId:null,pushLocalMessage(l){this.localMessages.push(l)},
init(){try{const u=document.getElementById("ragchat-init-data");
if(u){const v=JSON.parse(u.textContent);
this.sidebarConversations=v.conversations||[],this._actionAgentMap=v.actionAgentMap||{},this.roteiroAgentId=v.roteiroAgentId??null}}catch(u){console.warn("[ragChat] failed to parse init data:",u)}this.speechSupported="webkitSpeechRecognition"in window||"SpeechRecognition"in window,Alpine.store("contextWarning",(this.$wire.contextCharCount??0)>6e5),this._lastConversationId=this.$wire.get("conversationId"),Livewire.hook("morph.updated",({component:u})=>{const v=this.$wire.get("conversationId");
v!==this._lastConversationId&&(this._lastConversationId=v,this.localMessages=[],this.localConversationId=null,this.switchingChat=!1,this.hasSentMessage=!!v,this.traceVisible=!1,this.traceData={},Alpine.store("contextWarning",(this.$wire.contextCharCount??0)>6e5))}),window.addEventListener("conversations-updated",u=>{var v;
this.sidebarConversations=((v=u.detail)==null?void 0:v.conversations)??[]});
const l=document.getElementById("chat-messages");
l&&new MutationObserver(()=>{l.querySelectorAll(".dc-msg").length,this.localMessages.length}).observe(l,{childList:!0,subtree:!0}),Livewire.on("update-url",({conversationId:u})=>{const v=new URL(window.location);
u?v.searchParams.set("c",u):v.searchParams.delete("c"),window.history.replaceState({},"",v)}),Livewire.on("show-trace",({trace:u})=>{this.openTrace(u)}),Livewire.on("copy-clean-script-result",({text:u,error:v})=>{this.onCopyCleanScriptResult({text:u,error:v})}),Livewire.on("avatar-clone-result",({status:u,message:v,errorCode:x})=>{this.onAvatarCloneResult(u,v,x)}),Livewire.on("avatar-clone-confirm",({messageId:u,profiles:v,selectedProfileId:x})=>{this.openCloneConfirm(u,v,x)}),Livewire.on("avatar-clone-script",({text:u,fallback:v,error:x})=>{this.onCloneScriptLoaded(u,v,x)});
const d=new URLSearchParams(window.location.search).get("cite_viral");
if(d){this.$nextTick(()=>{const x=(this.$wire.get("attachedReferences")||[]).find(y=>String(y.id)===d&&y.source==="result");
if(x){const y=this.$refs.chatInput;
if(y){const b=document.createElement("span");
b.className="dc-mention-tag",b.contentEditable="false",b.dataset.refId=x.id,b.dataset.refSource="result",b.textContent=x.title,y.appendChild(b),y.appendChild(document.createTextNode(" ")),y.focus();
const _=document.createRange();
_.selectNodeContents(y),_.collapse(!1);
const C=window.getSelection();
C.removeAllRanges(),C.addRange(_),this.syncQuestion()}}});
const u=new URL(window.location);
u.searchParams.delete("cite_viral"),window.history.replaceState({},"",u)}const h=new URLSearchParams(window.location.search).get("cite_profile");
if(h){this.$nextTick(()=>{const x=(this.$wire.get("attachedReferences")||[]).find(y=>String(y.id)===h&&y.source==="search");
if(x){const y=this.$refs.chatInput;
if(y){const b=document.createElement("span");
b.className="dc-mention-tag",b.contentEditable="false",b.dataset.refId=x.id,b.dataset.refSource="search",b.textContent=x.title,y.appendChild(b),y.appendChild(document.createTextNode(" ")),y.focus();
const _=document.createRange();
_.selectNodeContents(y),_.collapse(!1);
const C=window.getSelection();
C.removeAllRanges(),C.addRange(_),this.syncQuestion()}}});
const u=new URL(window.location);
u.searchParams.delete("cite_profile"),window.history.replaceState({},"",u)}this.$refs.chatMessages&&this.$refs.chatMessages.addEventListener("click",u=>{const v=u.target.closest(".dc-action-btn");
if(!v)return;
u.preventDefault();
const x=v.dataset.action,y=JSON.parse(v.dataset.params);
this.handleActionButton(x,y)})},traceData:{},loadingTraceId:null,loadingCleanCopyId:null,cleanCopySuccessId:null,roteiroAgentId:null,cleanScriptVisible:!1,cleanScriptLoading:!1,cleanScriptText:"",cleanScriptCopied:!1,recordingCloneId:null,cloneConfirmVisible:!1,cloneConfirmMessageId:null,cloneConfirmProfiles:[],cloneConfirmSelectedId:null,cloneConfirmLoading:!1,cloneConfirmStep:"script",cloneConfirmScript:"",cloneConfirmScriptLoading:!1,sidebarOpen:!1,docsPanel:!1,deleteConfirm:{open:!1,id:null,title:"",busy:!1},atBottom:!0,creatingChat:!1,switchingChat:!1,speechSupported:!1,isListening:!1,speechRec:null,speechFinalBuf:"",_audioCtx:null,_audioAnalyser:null,_audioStream:null,_audioRaf:null,mentionOpen:!1,mentionResults:[],mentionIndex:0,mentionQuery:"",mentionStart:-1,mentionTimer:null,mentionPage:0,mentionHasMore:!1,mentionLoading:!1,mentionInitialLoading:!1,mentionActiveTab:"references",mentionSelected:[],researchGroupFilter:"Meu Público",researchSortFilter:"recent",researchVariableFilter:null,researchVariables:[],isDraggingDoc:!1,docUploading:!1,docUploadError:"",docPollTimer:null,typingPhrases:["Analisando sua pergunta","Buscando nos documentos","Consultando a base de conhecimento","Processando na fila","Quase la"],typingIndex:0,toolLabels:{search_documents:"🔍 Buscando nos documentos internos",search_headline:"📋 Buscando estruturas de headline","search_headline.avaliar":"🤖 IA avaliando estruturas para o contexto",search_web:"🌐 Buscando na web",fetch_instagram_profile:"📸 Buscando perfil do Instagram",fetch_instagram_reels:"🎬 Buscando reels do Instagram","search_web.niche":"🏥 Nicho saude detectado → PubMed","search_web.disambiguating":"🔎 Identificando assunto (termo vago)","search_web.disambiguated":"✅ Assunto identificado","search_web.results":"📋 Resultados encontrados","search_web.scraping":"📄 Extraindo conteudo da fonte","search_web.scrape_failed":"⚠️ Fonte inacessivel",nucleo_influencia:"👤 Consultando nucleo de influencia",consultar_gatilhos:"⚡ Estudando gatilhos da atencao",buscar_estruturas:"📚 Buscando estruturas de headlines","buscar_estruturas.avaliar":"🤖 IA selecionando melhores estruturas",consultar_variaveis_perfil:"📊 Consultando variáveis do perfil",consultar_estruturas_perfil:"🧬 Consultando estruturas do perfil",criar_headline:"✍️ Criando headline","criar_headline.gerar":"🎯 Gerando 5 variações","criar_headline.qa":"🔬 QA selecionando a melhor",consultar_pesquisa_viral:"🔥 Consultando pesquisa viral",gerar_headlines:"✍️ Gerando headlines","gerar_headlines.generate":"🎯 Gerando headlines candidatas","gerar_headlines.qualify":"🔬 QA — selecionando as melhores",qualificar_headline:"🔬 Qualificando headline (QA)",pesquisar_materia_prima:"🧠 Pesquisando materia-prima",estruturar_roteiro:"📝 Estruturando roteiro",refinar_copy:"✨ Refinando copy",avaliar_qualidade:"📊 Avaliando qualidade"},toolClassMap:{search_headline:"SearchHeadlineDocsTool","search_headline.avaliar":"SearchHeadlineDocsTool",search_web:"SearchWebTool",nucleo_influencia:"ConsultarNucleoInfluenciaTool",consultar_variaveis_perfil:"ConsultarVariaveisPerfilTool",consultar_estruturas_perfil:"ConsultarEstruturasPerfilTool",criar_headline:"CriarHeadlineTool","criar_headline.gerar":"CriarHeadlineTool","criar_headline.qa":"CriarHeadlineTool",consultar_pesquisa_viral:"ConsultarPesquisaViralTool",gerar_headlines:"GerarHeadlinesTool","gerar_headlines.generate":"GerarHeadlinesTool","gerar_headlines.qualify":"GerarHeadlinesTool","gerar_headlines.find_templates":"FindTemplates","gerar_headlines.validate_templates":"ValidateTemplates","gerar_headlines.find_variables":"FindVariables","gerar_headlines.validate_variables":"ValidateVariables","gerar_headlines.find_triggers":"FindTriggers","gerar_headlines.validate_triggers":"ValidateTriggers",search_marketing_process:"SearchMarketingProcessTool"},toolClassName(l){return this.toolClassMap[l]??l},getToolSubSteps(l){var h;
if(!((h=this.traceData)!=null&&h.rag_steps))return[];
const d=l.replace(/_tool$/,"");
return this.traceData.rag_steps.filter(u=>u.tool===d||u.tool.startsWith(d+"."))},resizeInput(l){},handleInput(l){const d=window.getSelection();
if(!d.rangeCount||!d.isCollapsed)return;
const h=d.anchorNode,u=d.anchorOffset;
if(!h||h.nodeType!==Node.TEXT_NODE)return;
const v=h.textContent,x=v.lastIndexOf("@",u-1);
if(x!==-1&&x===u-1){const y=x>0?v[x-1]:" ";
if(y===" "||y===`
`||x===0){h.textContent=v.substring(0,x)+v.substring(u);
const b=document.createRange();
b.setStart(h,x),b.collapse(!0),d.removeAllRanges(),d.addRange(b),this.openMentionModal()}}},
isRoteiroAgent(){var l;
return((l=this._actionAgentMap)==null?void 0:l.roteiro)==this.$wire.selectedAgentId},
openMentionModal(){this.mentionActiveTab==="cerebro"&&!this.isRoteiroAgent()&&(this.mentionActiveTab="references"),this.mentionOpen=!0,this.mentionResults=[],this.mentionIndex=0,this.mentionSelected=[],this.mentionPage=0,this.mentionHasMore=!1,this.mentionInitialLoading=!0,this.fetchMentions(""),this.$nextTick(()=>{const l=document.querySelector(".dc-mention-modal-search input");
l&&(l.value="",l.focus())})},switchMentionTab(l){this.mentionActiveTab!==l&&(this.mentionActiveTab=l,this.mentionResults=[],this.mentionIndex=0,this.mentionPage=0,this.mentionHasMore=!1,this.mentionQuery="",this.researchGroupFilter="Meu Público",this.researchVariableFilter=null,this.researchVariables=[],this.mentionInitialLoading=!0,this.$nextTick(()=>{const d=document.querySelector(".dc-mention-modal-search input");
d&&(d.value="",d.focus())}),l==="research"&&this.loadResearchVariables(),this.fetchMentions(""),this.managePollingDocs())},async fetchPage(l,d){return this.mentionActiveTab==="documents"?await this.$wire.searchUserDocuments(l,d):this.mentionActiveTab==="research"?await this.$wire.searchMyResearch(l,this.researchGroupFilter,d,this.researchSortFilter,this.researchVariableFilter):this.mentionActiveTab==="cerebro"?await this.$wire.searchMyCerebro(l,d):await this.$wire.searchMentions(l,d)},
filteredResults(){return this.mentionResults},async loadResearchVariables(){this.researchVariables=await this.$wire.getResearchVariables(this.researchGroupFilter)},switchResearchGroup(l){this.researchGroupFilter!==l&&(this.researchGroupFilter=l,this.researchVariableFilter=null,this.researchVariables=[],this.mentionResults=[],this.mentionIndex=0,this.mentionPage=0,this.mentionHasMore=!1,this.mentionInitialLoading=!0,this.loadResearchVariables(),this.fetchMentions(this.mentionQuery))},switchResearchVariable(l){this.researchVariableFilter=this.researchVariableFilter===l?null:l,this.mentionResults=[],this.mentionIndex=0,this.mentionPage=0,this.mentionHasMore=!1,this.mentionInitialLoading=!0,this.fetchMentions(this.mentionQuery)},switchResearchSort(l){this.researchSortFilter!==l&&(this.researchSortFilter=l,this.mentionResults=[],this.mentionIndex=0,this.mentionPage=0,this.mentionHasMore=!1,this.mentionInitialLoading=!0,this.fetchMentions(this.mentionQuery))},fetchMentions(l){clearTimeout(this.mentionTimer),this.mentionQuery=l,this.mentionTimer=setTimeout(async()=>{this.mentionPage=0;
const d=await this.fetchPage(l,0);
this.mentionResults=(d==null?void 0:d.items)||d||[],this.mentionHasMore=(d==null?void 0:d.hasMore)||!1,this.mentionIndex=0,this.mentionInitialLoading=!1,this.managePollingDocs()},150)},async loadMoreMentions(){if(this.mentionLoading||!this.mentionHasMore)return;
this.mentionLoading=!0,this.mentionPage++;
const l=await this.fetchPage(this.mentionQuery,this.mentionPage);
this.mentionResults=[...this.mentionResults,...(l==null?void 0:l.items)||[]],this.mentionHasMore=(l==null?void 0:l.hasMore)||!1,this.mentionLoading=!1},handleDocFileInput(l){var h;
const d=(h=l.target.files)==null?void 0:h[0];
d&&this.uploadDocument(d),l.target.value=""},handleDocDrop(l){var h,u;
const d=(u=(h=l.dataTransfer)==null?void 0:h.files)==null?void 0:u[0];
d&&this.uploadDocument(d)},async uploadDocument(l){var u;
this.docUploadError="";
const d=["pdf","docx","txt","md","csv"],h=(l.name.split(".").pop()||"").toLowerCase();
if(!d.includes(h)){this.docUploadError="Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.";
return}if(l.size>20*1024*1024){this.docUploadError="Arquivo maior que 20MB.";
return}this.docUploading=!0;
try{const v=new FormData;
v.append("file",l);
const x=(u=document.querySelector('meta[name="csrf-token"]'))==null?void 0:u.getAttribute("content"),y=await fetch(this._docUploadUrl,{method:"POST",headers:{"X-CSRF-TOKEN":x,Accept:"application/json"},body:v,credentials:"same-origin"});
if(y.ok){const b=await y.json(),_={id:b.id,source:"rag_document",type:"document",title:b.title,meta:b.meta||"Processando…",status:b.status,ready:!1};
this.mentionResults=[_,...this.mentionResults],this.managePollingDocs()}else{const b=await y.json().catch(()=>({}));
this.docUploadError=b.message||"Falha no upload."}}catch{this.docUploadError="Erro de rede no upload."}finally{this.docUploading=!1}},
managePollingDocs(){clearInterval(this.docPollTimer),this.docPollTimer=null,!(this.mentionActiveTab!=="documents"||!this.mentionResults.some(d=>d.ready===!1||d.status==="pending"||d.status==="processing"))&&(this.docPollTimer=setInterval(async()=>{if(!this.mentionOpen||this.mentionActiveTab!=="documents"){clearInterval(this.docPollTimer),this.docPollTimer=null;
return}const d=await this.$wire.searchUserDocuments(this.mentionQuery,0),h=(d==null?void 0:d.items)||[];
this.mentionResults=h,h.some(v=>v.ready===!1)||(clearInterval(this.docPollTimer),this.docPollTimer=null)},3e3))},toggleMentionSelection(l){const d=(l.source||"config")+"_"+l.id,h=this.mentionSelected.findIndex(u=>(u.source||"config")+"_"+u.id===d);
h===-1?this.mentionSelected.push(l):this.mentionSelected.splice(h,1)},isMentionSelected(l){const d=(l.source||"config")+"_"+l.id;
return this.mentionSelected.some(h=>(h.source||"config")+"_"+h.id===d)},
confirmMentionSelection(){if(!this.mentionSelected.length)return;
const l=this.$refs.chatInput,d=window.getSelection();
let h=null;
d.rangeCount&&l.contains(d.anchorNode)&&(h=d.getRangeAt(0).cloneRange(),h.collapse(!1)),this.mentionSelected.forEach(u=>{const v=document.createElement("span");
if(v.className="dc-mention-tag",v.contentEditable="false",v.dataset.refId=u.id,v.dataset.refSource=u.source||"config",v.textContent=u.title,h){h.insertNode(v),h.setStartAfter(v),h.collapse(!0);
const x=document.createTextNode(" ");
h.insertNode(x),h.setStartAfter(x),h.collapse(!0)}else l.appendChild(v),l.appendChild(document.createTextNode(" "));
this.$wire.attachReference(u.id,u.source||"config")}),h&&(d.removeAllRanges(),d.addRange(h)),l.focus(),this.syncQuestion(),this.mentionSelected=[],this.mentionOpen=!1,this.mentionResults=[]},selectMention(l){const d=this.$refs.chatInput,h=document.createElement("span");
h.className="dc-mention-tag",h.contentEditable="false",h.dataset.refId=l.id,h.dataset.refSource=l.source||"config",h.textContent=l.title;
const u=window.getSelection();
let v=!1;
if(u.rangeCount&&d.contains(u.anchorNode)){const x=u.getRangeAt(0);
x.collapse(!1),x.insertNode(h);
const y=document.createTextNode(" ");
h.after(y),x.setStartAfter(y),x.collapse(!0),u.removeAllRanges(),u.addRange(x),v=!0}v||(d.appendChild(h),d.appendChild(document.createTextNode(" "))),d.focus(),this.$wire.attachReference(l.id,l.source||"config"),this.syncQuestion(),this.mentionOpen=!1,this.mentionResults=[]},handleTagDelete(l,d){const h=window.getSelection();
if(!h.rangeCount||!h.isCollapsed)return;
const u=h.anchorNode,v=h.anchorOffset;
let x=null;
if(d==="backspace"){if(u.nodeType===Node.TEXT_NODE&&v===0){const y=u.previousSibling;
y&&y.classList&&y.classList.contains("dc-mention-tag")&&(x=y)}else if(u.nodeType===Node.ELEMENT_NODE&&v>0){const y=u.childNodes[v-1];
y&&y.classList&&y.classList.contains("dc-mention-tag")&&(x=y)}}else if(u.nodeType===Node.TEXT_NODE&&v===u.textContent.length){const y=u.nextSibling;
y&&y.classList&&y.classList.contains("dc-mention-tag")&&(x=y)}else if(u.nodeType===Node.ELEMENT_NODE&&v<u.childNodes.length){const y=u.childNodes[v];
y&&y.classList&&y.classList.contains("dc-mention-tag")&&(x=y)}if(x){l.preventDefault();
const y=parseInt(x.dataset.refId),b=x.dataset.refSource||"config";
x.remove(),this.$wire.detachReference(y,b),this.syncQuestion()}},
syncQuestion(){const l=this.$refs.chatInput;
this.$wire.set("question",l.textContent||"")},
toggleSpeech(){if(this.speechSupported){if(this.isListening){this.stopSpeech();
return}this.startSpeech()}},async startSpeech(){var h;
const l=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!l)return;
try{const u=await navigator.mediaDevices.getUserMedia({audio:!0});
this._audioStream=u,this._audioCtx=new(window.AudioContext||window.webkitAudioContext);
const v=this._audioCtx.createMediaStreamSource(u),x=this._audioCtx.createAnalyser();
x.fftSize=64,x.smoothingTimeConstant=.7,v.connect(x),this._audioAnalyser=x}catch(u){console.warn("[speech] mic stream falhou, visualizador desabilitado:",u.message)}const d=new l;
d.lang="pt-BR",d.continuous=!0,d.interimResults=!1,d.onresult=u=>{let v="";
for(let x=u.resultIndex;
x<u.results.length;
x++)u.results[x].isFinal&&(v+=u.results[x][0].transcript);
v&&this.insertSpeechText(v)},d.onerror=u=>{console.warn("[speech] erro:",u.error),this.stopSpeech()},d.onend=()=>{this.stopSpeech()};
try{d.start(),this.speechRec=d,this.isListening=!0,(h=this.$refs.chatInput)==null||h.focus(),this._startWaveAnimation()}catch(u){console.warn("[speech] falha ao iniciar:",u),this.stopSpeech()}},
stopSpeech(){var l;
try{(l=this.speechRec)==null||l.stop()}catch{}this._stopWaveAnimation(),this._audioStream&&(this._audioStream.getTracks().forEach(d=>d.stop()),this._audioStream=null),this._audioCtx&&(this._audioCtx.close().catch(()=>{}),this._audioCtx=null,this._audioAnalyser=null),this.isListening=!1,this.speechRec=null},
_startWaveAnimation(){const l=this._audioAnalyser,d=this.$refs.voiceWave;
if(!d)return;
const h=d.querySelectorAll(".dc-voice-wave-bar");
if(!h.length)return;
const u=l?l.frequencyBinCount:0,v=l?new Uint8Array(u):null,x=()=>{if(this._audioRaf=requestAnimationFrame(x),l&&v){l.getByteFrequencyData(v);
const y=Math.max(1,Math.floor(u/h.length));
h.forEach((b,_)=>{const C=v[_*y]||0,O=Math.max(4,C/255*28);
b.style.height=O+"px"})}else h.forEach(y=>{y.style.height=4+Math.random()*20+"px"})};
x()},
_stopWaveAnimation(){this._audioRaf&&(cancelAnimationFrame(this._audioRaf),this._audioRaf=null);
const l=this.$refs.voiceWave;
l&&l.querySelectorAll(".dc-voice-wave-bar").forEach(d=>{d.style.height="4px"})},insertSpeechText(l){const d=this.$refs.chatInput;
if(!d)return;
const h=l.trim();
if(!h)return;
const u=window.getSelection(),v=u.rangeCount&&d.contains(u.anchorNode),y=(d.textContent.length>0&&!/\s$/.test(d.textContent)?" ":"")+h+" ",b=document.createTextNode(y);
if(v){const _=u.getRangeAt(0);
_.collapse(!1),_.insertNode(b),_.setStartAfter(b),_.collapse(!0),u.removeAllRanges(),u.addRange(_)}else{d.appendChild(b);
const _=document.createRange();
_.selectNodeContents(d),_.collapse(!1),u.removeAllRanges(),u.addRange(_)}this.syncQuestion()},removeTagFromInput(l,d){this.$refs.chatInput.querySelectorAll(".dc-mention-tag").forEach(v=>{parseInt(v.dataset.refId)===l&&(v.dataset.refSource||"config")===d&&v.remove()}),this.syncQuestion()},
getQuestionWithMarkers(){const l=this.$refs.chatInput;
let d="";
const h=u=>{u.nodeType===Node.TEXT_NODE?d+=u.textContent:u.classList&&u.classList.contains("dc-mention-tag")?d+="@["+u.textContent+"]":u.childNodes.forEach(h)};
return l.childNodes.forEach(h),d.trim()},formatUserMessage(l){return l?l.replace(/&/g,"&amp;
").replace(/</g,"&lt;
").replace(/>/g,"&gt;
").replace(/@\[([^\]]+)\]/g,'<span class="dc-mention-tag-display">$1</span>'):""},processActionButtons(l){if(!l)return l;
const d={roteiro:"Criar roteiro a partir desta headline",roteiro_edit:"Criar roteiro com headline editável",select_reel:"Usar este reel como base"};
return l.replace(/\{\{action:(\w+)\|([^}]+)\}\}/g,(h,u,v)=>{const x={};
v.split("|").forEach(P=>{const L=P.indexOf("=");
L>-1&&(x[P.slice(0,L).trim()]=P.slice(L+1).trim())});
const y=JSON.stringify(x).replace(/"/g,"&quot;
");
if(u==="select_reel")return`<button class="dc-action-btn dc-action-btn-reel" data-action="select_reel" data-params="${y}" title="Usar este reel como base"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5l10 -10"/></svg></button>`;
const b=d[u]||u,_=d[u+"_edit"]||"Editar e enviar",C=`<button class="dc-action-btn" data-action="${u}" data-params="${y}" title="${b}"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M15 10l4.553 -2.276a1 1 0 0 1 1.447 .894v6.764a1 1 0 0 1 -1.447 .894l-4.553 -2.276v-4z"/><path d="M3 6m0 2a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2z"/></svg></button>`,O=`<button class="dc-action-btn dc-action-btn-edit" data-action="${u}_edit" data-params="${y}" title="${_}"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/></svg></button>`;
return C+O})},handleActionButton(l,d){if(this.streaming)return;
const h=this._actionAgentMap||{};
if(l.endsWith("_edit")){const x=l.replace("_edit",""),y=h[x]||null;
y&&this.$wire.set("selectedAgentId",y);
const b=d.id||"",C=`Crie um roteiro para a headline: "${d.headline||""}" (estrutura_id: ${b})`;
this.$refs.chatInput.innerText=C,this.$refs.chatInput.focus();
const O=document.createRange();
O.selectNodeContents(this.$refs.chatInput),O.collapse(!1);
const P=window.getSelection();
P.removeAllRanges(),P.addRange(O);
return}const u=h[l]||null;
u&&this.$wire.set("selectedAgentId",u);
let v;
if(l==="roteiro"){const x=d.id||"";
v=`Crie um roteiro para a headline: "${d.headline||""}" (estrutura_id: ${x})`}else if(l==="select_reel"){const x=d.reel||"1",y=d.caption||"";
v=`Quero usar o reel ${x}: "${y}"`}else v=`Execute ação ${l}: ${JSON.stringify(d)}`;
this.askViaSSE(v,u)},iceBreaker(l,d=null){this.askViaSSE(l,d||this.$wire.get("selectedAgentId"))},
getReferencesFromDom(){const d=this.$refs.chatInput.querySelectorAll(".dc-mention-tag"),h=[],u=new Set;
return d.forEach(v=>{const x=(v.dataset.refSource||"config")+"_"+v.dataset.refId;
u.has(x)||(u.add(x),h.push({source:v.dataset.refSource||"config",id:parseInt(v.dataset.refId)}))}),h},async askViaSSE(l=null,d=null){var L;
const h=l||this.getQuestionWithMarkers(),u=d||this.$wire.get("selectedAgentId"),v=this.localConversationId||this.$wire.get("conversationId");
if(!h||!u)return;
this.activeAbortController&&(this.activeAbortController.abort(),this.activeAbortController=null),this.streamId++;
const x=this.streamId,y=new AbortController;
this.activeAbortController=y;
const b=l?[]:this.getReferencesFromDom();
l||(this.$refs.chatInput.innerHTML="",this.$refs.chatInput.style.height="auto"),this.hasSentMessage=!0,this.pushLocalMessage({role:"user",content:h}),clearTimeout(this.renderTimer),this.renderTimer=null,this.typingHtml="",this.typingText="",this.resetSteps(),this.streamedText="",this.streaming=!0;
const _=this.$refs.chatMessages,C=(B=!1)=>{_&&(!B&&!this.atBottom||this.$nextTick(()=>_.scrollTo({top:_.scrollHeight})))};
this.atBottom=!0,C(!0);
const O=(L=document.querySelector('meta[name="csrf-token"]'))==null?void 0:L.content,P=this._streamUrl;
try{await window.fetchEventSource(P,{method:"POST",signal:y.signal,headers:{"Content-Type":"application/json","X-CSRF-TOKEN":O,Accept:"text/event-stream"},body:JSON.stringify({question:h,selected_agent_id:u,conversation_id:v,attached_reference_ids:b}),openWhenHidden:!0,onopen:async B=>{if(this.streamId===x&&!B.ok){const D=await B.text().catch(()=>"");
throw console.error("[SSE] onopen erro:",B.status,D),new Error("Erro na conexão: "+B.status)}},onmessage:B=>{if(this.streamId!==x||!B.data)return;
const D=JSON.parse(B.data);
switch(B.event){case"token":this.streamedText+=D.text,this.typingText=this.streamedText,clearTimeout(this.renderTimer),this.renderTimer=setTimeout(()=>{this.streamId===x&&(typeof marked<"u"&&(this.typingHtml=this.processActionButtons(marked.parse(this.streamedText))),C())},40);
break;
case"progress":this.streamedText||(this.typingText=D.message||"");
break;
case"rag_step":{const se=this.toolLabels[D.tool]??D.tool;
if(D.status==="start")this.steps.push({tool:D.tool,label:se,status:"start",data:D.data||{}}),this.stepsOpen=!0;
else if(D.status==="done"){const K=this.steps.findLastIndex(G=>G.tool===D.tool&&G.status==="start");
K!==-1&&(this.steps[K]={...this.steps[K],status:"done",data:{...this.steps[K].data,...D.data||{}}})}break}case"tool_start":{if(this.steps.findLastIndex(K=>K.tool===D.name&&K.status==="start")===-1){const K=this.toolLabels[D.name]??D.name;
this.steps.push({tool:D.name,label:K,status:"start",data:{}}),this.stepsOpen=!0}break}case"tool_end":{const se=this.steps.findLastIndex(K=>K.tool===D.name);
se!==-1&&(this.steps[se]={...this.steps[se],status:"done",data:{...this.steps[se].data,duration_ms:D.duration_ms}});
break}case"refining_start":{this.steps.push({tool:"refining",label:D.label+"...",kind:"refining",status:"start",data:{}}),this.stepsOpen=!0;
break}case"refining_end":{const se=this.steps.findLastIndex(K=>K.tool==="refining"&&K.status==="start");
se!==-1&&(this.steps[se]={...this.steps[se],status:"done"});
break}case"review_start":{const se=`review:${D.reviewer_id}:${D.attempt}`,K=`Analisando: ${D.reviewer_name}`;
this.steps.push({tool:se,label:K,kind:"review",status:"start",data:{reviewer_id:D.reviewer_id,reviewer_name:D.reviewer_name,reviewer_description:D.reviewer_description||null,attempt:D.attempt,max_attempts:D.max_attempts}}),this.stepsOpen=!0;
break}case"review_end":{const se=`review:${D.reviewer_id}`,K=this.steps.findLastIndex(G=>typeof G.tool=="string"&&G.tool.startsWith(`${se}:`)&&G.status==="start");
K!==-1&&(this.steps[K]={...this.steps[K],status:D.approved?"approved":"rejected",label:D.approved?`Aprovado: ${this.steps[K].data.reviewer_name}`:`Reprovou: ${this.steps[K].data.reviewer_name}`,data:{...this.steps[K].data,approved:D.approved,feedback:D.feedback||null,duration_ms:D.duration_ms,metadata:D.metadata||null}});
break}case"review_retry":{this.steps.push({tool:`review:retry:${D.attempt}`,label:`Refazendo texto (tentativa ${D.attempt}/${D.max_attempts})`,kind:"review_retry",status:"start",data:{attempt:D.attempt,max_attempts:D.max_attempts,reason:D.reason||""}}),this.stepsOpen=!0,this.streamedText="",this.typingHtml="";
break}case"review_warn":{this.steps.push({tool:`review:warn:${D.reviewer_id}`,label:`Aviso: ${D.reviewer_name}`,kind:"review_warn",status:"warn",data:{reviewer_id:D.reviewer_id,reviewer_name:D.reviewer_name,feedback:D.feedback||""}});
break}case"completed":if(this.stopTyping(),this.streaming=!1,this.activeAbortController=null,this.localMessages.push({role:"assistant",content:D.message||this.streamedText,html:this.processActionButtons(D.message_html||this.streamedText),id:D.message_id||null,isRoteiro:String(u)===String(this.roteiroAgentId)}),D.context_chars&&Alpine.store("contextWarning",D.context_chars>6e5),this.localConversationId=D.conversation_id,D.conversation_id){const se=new URL(window.location);
se.searchParams.set("c",D.conversation_id),window.history.replaceState({},"",se)}this.$wire.call("refreshConversationList"),C();
break;
case"error":this.stopTyping(),this.streaming=!1,this.activeAbortController=null,this.pushLocalMessage({role:"assistant",content:D.message||"Erro ao processar.",html:D.message||"Erro ao processar."});
{const se=this.steps.findLastIndex(K=>K.tool==="refining"&&K.status==="start");
se!==-1&&(this.steps[se]={...this.steps[se],status:"rejected",label:"Revisão bloqueada"})}break}},onerror:B=>{if(this.streamId===x)throw console.error("[SSE] onerror:",B),this.stopTyping(),this.streaming=!1,this.activeAbortController=null,this.pushLocalMessage({role:"assistant",content:"Conexão perdida. Tente novamente.",html:"Conexão perdida. Tente novamente."}),B}})}catch(B){if((B==null?void 0:B.name)==="AbortError")return;
this.streamId===x&&this.streaming&&(this.stopTyping(),this.streaming=!1,this.activeAbortController=null)}},
startTyping(){this.typingIndex=0,this.typingText=this.typingPhrases[0]+"...",this.typingTimer=setInterval(()=>{this.typingIndex=(this.typingIndex+1)%this.typingPhrases.length,this.typingText=this.typingPhrases[this.typingIndex]+"..."},3e3)},
stopTyping(){clearInterval(this.typingTimer),clearTimeout(this.renderTimer),this.typingTimer=null,this.renderTimer=null,this.typingText="",this.typingHtml="",this.streamedText=""},
resetSteps(){this.steps=[],this.stepsOpen=!0,this.startTyping()},openTrace(l){this.traceData=l&&!Array.isArray(l)?l:{},this.traceVisible=!0,this.loadingTraceId=null},
closeTrace(){this.traceVisible=!1,this.traceData={}},onCopyCleanScriptResult({text:l,error:d}){if(this.loadingCleanCopyId=null,this.cleanScriptLoading=!1,d||!l){this.cleanScriptVisible=!1,alert(d||"Erro ao processar o roteiro.");
return}this.cleanScriptText=l,this.cleanScriptCopied=!1},
copyCleanScriptText(){navigator.clipboard.writeText(this.cleanScriptText).then(()=>{this.cleanScriptCopied=!0,setTimeout(()=>{this.cleanScriptCopied=!1},2e3)})},onAvatarCloneResult(l,d,h){if(this.recordingCloneId=null,l==="success"){this.closeCloneConfirm(),window.toastr&&toastr.success(d);
return}if(h==="insufficient_credits"){this.cloneConfirmLoading=!1,this.showRechargePanel();
return}this.closeCloneConfirm(),window.toastr?toastr.error(d):alert(d)},openCloneConfirm(l,d,h){var u;
this.recordingCloneId=null,this.cloneConfirmMessageId=l,this.cloneConfirmScript="",this.cloneConfirmStep="script",this.cloneConfirmProfiles=d||[],this.cloneConfirmSelectedId=h??((u=d==null?void 0:d[0])==null?void 0:u.id)??null,this.cloneConfirmLoading=!1,this.cloneConfirmVisible=!0,this.cloneConfirmScriptLoading=!0,this.$wire.loadCloneScript(l)},onCloneScriptLoaded(l,d,h){if(this.cloneConfirmScriptLoading=!1,!l){this.closeCloneConfirm(),window.toastr&&toastr.error(h||"Não foi possível preparar o roteiro.");
return}this.cloneConfirmScript=l,d&&window.toastr&&toastr.warning("Não deu pra limpar o roteiro com IA — revise o texto antes de gerar.")},autosizeCloneScript(l){l&&(l.style.height="auto",l.style.height=Math.min(l.scrollHeight+2,520)+"px")},
goToCloneAvatarStep(){this.cloneConfirmScriptLoading||!this.cloneConfirmScript.trim()||(this.cloneConfirmStep="avatar")},
backToCloneScriptStep(){this.cloneConfirmStep="script"},
selectedCloneProfile(){return this.cloneConfirmProfiles.find(l=>l.id===this.cloneConfirmSelectedId)||null},
confirmRecordClone(){!this.cloneConfirmMessageId||!this.cloneConfirmSelectedId||this.cloneConfirmScript.trim()&&(this.cloneConfirmLoading=!0,this.$wire.recordWithClone(this.cloneConfirmMessageId,this.cloneConfirmSelectedId,this.cloneConfirmScript.trim()))},
closeCloneConfirm(){this.cloneConfirmVisible=!1,this.cloneConfirmMessageId=null,this.cloneConfirmScript="",this.cloneConfirmScriptLoading=!1,this.cloneConfirmStep="script",this.cloneConfirmProfiles=[],this.cloneConfirmSelectedId=null,this.cloneConfirmLoading=!1,this.closeRechargePanel()},async showRechargePanel(){var l,d;
if(this.rechargeVisible=!0,this.rechargeLoading=!0,this.rechargeHasCard=!0,this.rechargePackages=[],this.rechargeSelectedId=null,!this._creditsUrl){this.rechargeLoading=!1;
return}try{const u=await(await fetch(this._creditsUrl,{headers:{Accept:"application/json"}})).json();
this.rechargeHasCard=!!u.has_payment_method,this.rechargePackages=u.packages||[],this.rechargeSelectedId=((l=this.rechargePackages[1])==null?void 0:l.id)??((d=this.rechargePackages[0])==null?void 0:d.id)??null}catch{window.toastr&&toastr.error("Não foi possível carregar os pacotes de crédito.")}finally{this.rechargeLoading=!1}},selectRechargePackage(l){this.rechargeSelectedId=l},
goToFaturamento(){this._faturamentoUrl&&(window.location.href=this._faturamentoUrl)},async confirmRecharge(){var l;
if(!(!this.rechargeSelectedId||!this._rechargesUrl)){this.rechargeLoading=!0;
try{const d=await fetch(this._rechargesUrl,{method:"POST",headers:{"Content-Type":"application/json",Accept:"application/json","X-CSRF-TOKEN":((l=document.querySelector('meta[name="csrf-token"]'))==null?void 0:l.getAttribute("content"))||""},body:JSON.stringify({credit_package_id:this.rechargeSelectedId})}),h=await d.json().catch(()=>({}));
if(!d.ok){window.toastr&&toastr.error(h.message||"Não foi possível processar a recarga.");
return}window.toastr&&toastr.success(h.message||'Recarga concluída! Clique em "Gerar vídeo" pra continuar.'),this.closeRechargePanel()}catch{window.toastr&&toastr.error("Erro inesperado ao recarregar.")}finally{this.rechargeLoading=!1}}},
closeRechargePanel(){this.rechargeVisible=!1,this.rechargeLoading=!1,this.rechargeHasCard=!0,this.rechargePackages=[],this.rechargeSelectedId=null},
closeCleanScript(){this.cleanScriptVisible=!1,this.cleanScriptLoading=!1,this.cleanScriptText=""},async loadToolDetail(l,d,h){var v,x;
const u=l.querySelector(".dc-tool-detail");
if(u){u.textContent="Carregando detalhes...",u.style.cssText="color:#8b949e; font-size:.72rem; padding:8px;
";
try{const y=await this.$wire.loadToolDetail(this.traceData._messageId,d,h);
y?(u.style.cssText="",u.innerHTML=y):(u.textContent="Sem dados",u.style.cssText="color:#f85149; padding:8px;
");
const b=this.traceData.rounds||[];
(x=(v=b[d])==null?void 0:v.tool_calls)!=null&&x[h]&&(b[d].tool_calls[h]._loaded=!0)}catch(y){u.textContent="Erro ao carregar: "+y.message,u.style.cssText="color:#f85149; padding:8px;
"}}},formatTraceDuration(l){return l?l>1e3?(l/1e3).toFixed(1)+"s":l+"ms":"-"},
formatTraceTokens(){if(!this.traceData.usage)return"-";
const l=this.traceData.usage,d=l.prompt_tokens||0,h=l.completion_tokens||0,u=l.total_tokens||d+h;
return"in: "+d.toLocaleString()+" · out: "+h.toLocaleString()+" · total: "+u.toLocaleString()},tryParseJson(l){if(l==null)return null;
if(typeof l=="object"||typeof l!="string")return l;
try{return JSON.parse(l)}catch{return l}},renderJsonTree(l,d=0,h=!1){const u=(y,b,_)=>"<"+y+(b?' class="'+b+'"':"")+">"+_+"</"+y+">",v=(y,b,_)=>"<"+y+(b?' class="'+b+'"':"")+(_||"")+">",x=y=>"</"+y+">";
if(l==null)return u("span","jt-null","null");
if(typeof l=="boolean")return u("span","jt-bool",l);
if(typeof l=="number")return u("span","jt-num",l);
if(typeof l=="string"){if(l.length>300){const y="jt-"+Math.random().toString(36).substr(2,9);
return u("span","jt-str",'"'+v("span","",' id="'+y+'-short"')+this.escHtml(l.substring(0,150))+v("button","jt-expand-str",` onclick="document.getElementById('`+y+"-short').style.display='none';
document.getElementById('"+y+`-full').style.display='inline';
"`)+"...+"+(l.length-150)+" chars"+x("button")+x("span")+v("span","",' id="'+y+'-full" style="display:none"')+this.escHtml(l)+x("span")+'"')}return u("span","jt-str",'"'+this.escHtml(l)+'"')}if(Array.isArray(l)){if(l.length===0)return u("span","jt-bracket","[]");
const y=h&&d<2?" open":"";
let b=l.map((_,C)=>{const O=C<l.length-1?u("span","jt-comma",","):"";
return u("div","jt-row",this.renderJsonTree(_,d+1,h)+O)}).join("");
return v("details","jt-details",y)+v("summary","jt-summary","")+u("span","jt-bracket","[")+u("span","jt-preview",l.length+" items")+u("span","jt-bracket","]")+x("summary")+u("div","jt-indent",b)+u("span","jt-bracket","]")+x("details")}if(typeof l=="object"){const y=Object.keys(l);
if(y.length===0)return u("span","jt-bracket","{}");
const b=h&&d<2?" open":"";
let _=y.map((O,P)=>{const L=P<y.length-1?u("span","jt-comma",","):"";
return u("div","jt-row",u("span","jt-key",'"'+this.escHtml(O)+'"')+u("span","jt-colon",": ")+this.renderJsonTree(l[O],d+1,h)+L)}).join("");
const C=y.slice(0,3).join(", ")+(y.length>3?", ...":"");
return v("details","jt-details",b)+v("summary","jt-summary","")+u("span","jt-bracket","{")+u("span","jt-preview",this.escHtml(C))+u("span","jt-bracket","}")+x("summary")+u("div","jt-indent",_)+u("span","jt-bracket","}")+x("details")}return u("span","",this.escHtml(String(l)))},escHtml(l){return String(l).replace(/&/g,"&amp;
").replace(/</g,"&lt;
").replace(/>/g,"&gt;
")},ragStepLabel(l){return this.toolLabels[l]??l},toolNameLabel(l){return{consultar_nucleo_influencia_tool:"Consultando perfil do cliente",consultar_gatilhos_tool:"Estudando gatilhos de atencao",buscar_estruturas_tool:"Buscando estruturas de headlines",consultar_pesquisa_viral_tool:"Consultando pesquisa viral",consultar_variaveis_perfil_tool:"Consultando variaveis do perfil",consultar_estruturas_perfil_tool:"Consultando estruturas do perfil",gerar_headlines_tool:"Gerando headlines",qualificar_headline_tool:"Qualificando headline (QA)",criar_headline_tool:"Criando headline",estruturar_roteiro_tool:"Estruturando roteiro",avaliar_qualidade_conteudo_tool:"Avaliando qualidade do conteudo",search_documents_tool:"Buscando nos documentos",list_documents_tool:"Listando documentos",search_web_tool:"Buscando na web",salvar_memoria_tool:"Salvando na memória",esquecer_memoria_tool:"Apagando da memória"}[l]??l.replace(/_tool$/,"").replace(/_/g," ")}}}document.addEventListener("livewire:request",e=>{var t,r,i,s,a;
if((i=(r=(t=e.detail)==null?void 0:t.payload)==null?void 0:r.calls)!=null&&i.some(c=>c.method==="ask")){const c=document.querySelector('[x-data^="ragChat"]');
(a=(s=c==null?void 0:c._x_dataStack)==null?void 0:s[0])!=null&&a.resetSteps&&c._x_dataStack[0].resetSteps()}});
document.addEventListener("livewire:updated",()=>{const e=document.getElementById("chat-messages");
if(!e)return;
e.scrollHeight-e.scrollTop-e.clientHeight<80&&e.scrollTo({top:e.scrollHeight,behavior:"smooth"})});
window.ragChat=Qp;
window.fetchEventSource=Jp;
localStorage.getItem("lqdDarkMode");
localStorage.getItem("docsViewMode");
localStorage.getItem("lqdNavbarShrinked");
window.Alpine=rc;
rc.plugin(Up);
document.addEventListener("alpine:init",()=>{});
co.start();
