// Inicializa o store ANTES do Alpine processar o DOM
    document.addEventListener('alpine:init', () => {
        Alpine.store('contextWarning', false);
    });

    // Links abrem em nova aba
    const renderer = new marked.Renderer();
    renderer.link = function({ href, title, tokens }) {
        const text = this.parser.parseInline(tokens);
        const titleAttr = title ? ` title="${title}"` : '';
        return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
    };
    marked.setOptions({ renderer });

    function ragChat(userId, appEnv) {
        console.log('[ragChat] function called, userId:', userId, 'appEnv:', appEnv);
        return {
            steps:       [],
            stepsOpen:   true,
            typingText:  '',
            typingTimer: null,
            streaming:   false,
            streamedText: '',
            typingHtml:  '',
            renderTimer: null,
            localMessages: [],
            localConversationId: null,
            traceVisible: false,
            pushLocalMessage(msg) {
                this.localMessages.push(msg);
            },

            init() {

                // Detectar suporte a Web Speech API
                this.speechSupported = ('webkitSpeechRecognition' in window) || ('SpeechRecognition' in window);


                // Limpar mensagens locais APENAS quando troca de conversa (não em qualquer morph)
                this._lastConversationId = this.$wire.get('conversationId');
                Livewire.hook('morph.updated', ({ component }) => {
                    const currentId = this.$wire.get('conversationId');
                    if (currentId !== this._lastConversationId) {
                        this._lastConversationId = currentId;
                        this.localMessages = [];
                        this.localConversationId = null;
                        Alpine.store('contextWarning', false);
                        this.switchingChat = false;
                    }
                });

                // Monitor DOM: detectar se mensagens somem
                const chatEl = document.getElementById('chat-messages');
                if (chatEl) {
                    const obs = new MutationObserver(() => {
                        const serverMsgs = chatEl.querySelectorAll('.dc-msg').length;
                        const localMsgs = this.localMessages.length;
                        console.log('[MSG-DEBUG] DOM mutation detected, server msgs in DOM:', serverMsgs, 'localMessages:', localMsgs, 'streaming:', this.streaming);
                    });
                    obs.observe(chatEl, { childList: true, subtree: true });
                }

                // Atualizar URL quando Livewire muda de conversa
                Livewire.on('update-url', ({ conversationId }) => {
                    const url = new URL(window.location);
                    if (conversationId) {
                        url.searchParams.set('c', conversationId);
                    } else {
                        url.searchParams.delete('c');
                    }
                    window.history.replaceState({}, '', url);
                });

                // Auto-inserir tag visual se veio com ?cite_viral=
                const citeViralId = new URLSearchParams(window.location.search).get('cite_viral');
                if (citeViralId) {
                    this.$nextTick(() => {
                        const refs = this.$wire.get('attachedReferences') || [];
                        const ref = refs.find(r => String(r.id) === citeViralId && r.source === 'result');
                        if (ref) {
                            const el = this.$refs.chatInput;
                            if (el) {
                                const tag = document.createElement('span');
                                tag.className = 'dc-mention-tag';
                                tag.contentEditable = 'false';
                                tag.dataset.refId = ref.id;
                                tag.dataset.refSource = 'result';
                                tag.textContent = ref.title;
                                el.appendChild(tag);
                                el.appendChild(document.createTextNode('\u00A0'));
                                el.focus();
                                const range = document.createRange();
                                range.selectNodeContents(el);
                                range.collapse(false);
                                const sel = window.getSelection();
                                sel.removeAllRanges();
                                sel.addRange(range);
                                this.syncQuestion();
                            }
                        }
                    });
                    const url = new URL(window.location);
                    url.searchParams.delete('cite_viral');
                    window.history.replaceState({}, '', url);
                }

                // Auto-inserir tag visual se veio com ?cite_profile=
                const citeProfileId = new URLSearchParams(window.location.search).get('cite_profile');
                if (citeProfileId) {
                    this.$nextTick(() => {
                        const refs = this.$wire.get('attachedReferences') || [];
                        const ref = refs.find(r => String(r.id) === citeProfileId && r.source === 'search');
                        if (ref) {
                            const el = this.$refs.chatInput;
                            if (el) {
                                const tag = document.createElement('span');
                                tag.className = 'dc-mention-tag';
                                tag.contentEditable = 'false';
                                tag.dataset.refId = ref.id;
                                tag.dataset.refSource = 'search';
                                tag.textContent = ref.title;
                                el.appendChild(tag);
                                el.appendChild(document.createTextNode(' '));
                                el.focus();
                                const range = document.createRange();
                                range.selectNodeContents(el);
                                range.collapse(false);
                                const sel = window.getSelection();
                                sel.removeAllRanges();
                                sel.addRange(range);
                                this.syncQuestion();
                            }
                        }
                    });
                    const url = new URL(window.location);
                    url.searchParams.delete('cite_profile');
                    window.history.replaceState({}, '', url);
                }

                // Event delegation para botões de ação em mensagens da IA
                this.$refs.chatMessages.addEventListener('click', (e) => {
                    const btn = e.target.closest('.dc-action-btn');
                    if (!btn) return;
                    e.preventDefault();
                    const action = btn.dataset.action;
                    const params = JSON.parse(btn.dataset.params);
                    this.handleActionButton(action, params);
                });
             },
            traceData:    {},
            loadingTraceId: null,
            sidebarOpen:  false,
            docsPanel:    false,
            deleteConfirm: { open: false, id: null, title: '', busy: false },
            atBottom:     true,
            creatingChat: false,
            switchingChat: false,

            // Speech-to-text state (Web Speech API)
            speechSupported: false,
            isListening:     false,
            speechRec:       null,
            speechFinalBuf:  '',
            _audioCtx:       null,
            _audioAnalyser:  null,
            _audioStream:    null,
            _audioRaf:       null,

            // @ mention state
            mentionOpen:    false,
            mentionResults: [],
            mentionIndex:   0,
            mentionQuery:   '',
            mentionStart:   -1,
            mentionTimer:   null,
            mentionPage:    0,
            mentionHasMore: false,
            mentionLoading: false,
            mentionInitialLoading: false,
            mentionActiveTab: 'references', // 'references' | 'documents' | 'research'
            mentionSelected: [], // itens selecionados para inserção em lote
            researchGroupFilter: 'Meu Público', // 'Sobre mim' | 'Meu Público' | 'Assuntos Virais'

            // Upload de documentos (aba Documentos)
            isDraggingDoc:  false,
            docUploading:   false,
            docUploadError: '',
            docPollTimer:   null,

            typingPhrases: [
                'Analisando sua pergunta',
                'Buscando nos documentos',
                'Consultando a base de conhecimento',
                'Processando na fila',
                'Quase la',
            ],
            typingIndex: 0,

            toolLabels: {
                'search_documents': '🔍 Buscando nos documentos internos',
                'search_headline':  '📋 Buscando estruturas de headline',
                'search_headline.avaliar':  '🤖 IA avaliando estruturas para o contexto',
                'search_web':                '🌐 Buscando na web',
                'fetch_instagram_profile':   '📸 Buscando perfil do Instagram',
                'fetch_instagram_reels':     '🎬 Buscando reels do Instagram',
                'search_web.niche':          '🏥 Nicho saude detectado → PubMed',
                'search_web.disambiguating': '🔎 Identificando assunto (termo vago)',
                'search_web.disambiguated':  '✅ Assunto identificado',
                'search_web.results':        '📋 Resultados encontrados',
                'search_web.scraping':       '📄 Extraindo conteudo da fonte',
                'search_web.scrape_failed':  '⚠️ Fonte inacessivel',
                'nucleo_influencia':                     '👤 Consultando nucleo de influencia',
                'consultar_gatilhos':                    '⚡ Estudando gatilhos da atencao',
                'buscar_estruturas':                     '📚 Buscando estruturas de headlines',
                'buscar_estruturas.avaliar':              '🤖 IA selecionando melhores estruturas',
                'consultar_variaveis_perfil':              '📊 Consultando variáveis do perfil',
                'consultar_estruturas_perfil':             '🧬 Consultando estruturas do perfil',
                'criar_headline':                         '✍️ Criando headline',
                'criar_headline.gerar':                   '🎯 Gerando 5 variações',
                'criar_headline.qa':                      '🔬 QA selecionando a melhor',
                'consultar_pesquisa_viral':               '🔥 Consultando pesquisa viral',
                'gerar_headlines':                       '✍️ Gerando headlines',
                'gerar_headlines.generate':               '🎯 Gerando headlines candidatas',
                'gerar_headlines.qualify':                '🔬 QA — selecionando as melhores',
                'qualificar_headline':                   '🔬 Qualificando headline (QA)',
                'pesquisar_materia_prima':               '🧠 Pesquisando materia-prima',
                'estruturar_roteiro':                    '📝 Estruturando roteiro',
                'refinar_copy':                          '✨ Refinando copy',
                'avaliar_qualidade':                     '📊 Avaliando qualidade',
            },

            toolClassMap: {
                'search_headline':               'SearchHeadlineDocsTool',
                'search_headline.avaliar':       'SearchHeadlineDocsTool',
                'search_web':                    'SearchWebTool',
                'nucleo_influencia':             'ConsultarNucleoInfluenciaTool',
                'consultar_variaveis_perfil':    'ConsultarVariaveisPerfilTool',
                'consultar_estruturas_perfil':   'ConsultarEstruturasPerfilTool',
                'criar_headline':                'CriarHeadlineTool',
                'criar_headline.gerar':          'CriarHeadlineTool',
                'criar_headline.qa':             'CriarHeadlineTool',
                'consultar_pesquisa_viral':      'ConsultarPesquisaViralTool',
                'gerar_headlines':               'GerarHeadlinesTool',
                'gerar_headlines.generate':      'GerarHeadlinesTool',
                'gerar_headlines.qualify':        'GerarHeadlinesTool',
                'gerar_headlines.find_templates': 'FindTemplates',
                'gerar_headlines.validate_templates': 'ValidateTemplates',
                'gerar_headlines.find_variables': 'FindVariables',
                'gerar_headlines.validate_variables': 'ValidateVariables',
                'gerar_headlines.find_triggers':  'FindTriggers',
                'gerar_headlines.validate_triggers': 'ValidateTriggers',
                'search_marketing_process':      'SearchMarketingProcessTool',
            },

            toolClassName(tool) {
                return this.toolClassMap[tool] ?? tool;
            },

            getToolSubSteps(toolName) {
                if (!this.traceData?.rag_steps) return [];
                const base = toolName.replace(/_tool$/, '');
                return this.traceData.rag_steps.filter(s => s.tool === base || s.tool.startsWith(base + '.'));
            },

            resizeInput(el) {
                // contenteditable cresce automaticamente; max-height no CSS controla o limite
            },

            handleInput(e) {
                const sel = window.getSelection();
                if (!sel.rangeCount || !sel.isCollapsed) return;

                const node = sel.anchorNode;
                const offset = sel.anchorOffset;
                if (!node || node.nodeType !== Node.TEXT_NODE) return;

                const text = node.textContent;
                const atIndex = text.lastIndexOf('@', offset - 1);

                if (atIndex !== -1 && atIndex === offset - 1) {
                    const charBefore = atIndex > 0 ? text[atIndex - 1] : ' ';
                    if (charBefore === ' ' || charBefore === '\n' || atIndex === 0) {
                        // Remover o @ do contenteditable
                        node.textContent = text.substring(0, atIndex) + text.substring(offset);
                        // Reposicionar cursor
                        const range = document.createRange();
                        range.setStart(node, atIndex);
                        range.collapse(true);
                        sel.removeAllRanges();
                        sel.addRange(range);

                        this.openMentionModal();
                    }
                }
            },

            openMentionModal() {
                this.mentionOpen = true;
                this.mentionResults = [];
                this.mentionIndex = 0;
                this.mentionSelected = [];
                this.mentionPage = 0;
                this.mentionHasMore = false;
                this.mentionInitialLoading = true;
                this.fetchMentions('');
                this.$nextTick(() => {
                    const input = document.querySelector('.dc-mention-modal-search input');
                    if (input) { input.value = ''; input.focus(); }
                });
            },

            switchMentionTab(tab) {
                if (this.mentionActiveTab === tab) return;
                this.mentionActiveTab = tab;
                this.mentionResults = [];
                this.mentionIndex  = 0;
                this.mentionPage   = 0;
                this.mentionHasMore = false;
                this.mentionQuery  = '';
                this.researchGroupFilter = 'Meu Público';
                this.mentionInitialLoading = true;
                this.$nextTick(() => {
                    const input = document.querySelector('.dc-mention-modal-search input');
                    if (input) { input.value = ''; input.focus(); }
                });
                this.fetchMentions('');
                this.managePollingDocs();
            },

            async fetchPage(query, page) {
                if (this.mentionActiveTab === 'documents') {
                    return await this.$wire.searchUserDocuments(query, page);
                }
                if (this.mentionActiveTab === 'research') {
                    return await this.$wire.searchMyResearch(query, this.researchGroupFilter, page);
                }
                return await this.$wire.searchMentions(query, page);
            },

            filteredResults() {
                return this.mentionResults;
            },

            switchResearchGroup(group) {
                if (this.researchGroupFilter === group) return;
                this.researchGroupFilter = group;
                this.mentionResults = [];
                this.mentionIndex = 0;
                this.mentionPage = 0;
                this.mentionHasMore = false;
                this.mentionInitialLoading = true;
                this.fetchMentions(this.mentionQuery);
            },

            fetchMentions(query) {
                clearTimeout(this.mentionTimer);
                this.mentionQuery = query;
                this.mentionTimer = setTimeout(async () => {
                    this.mentionPage = 0;
                    const response = await this.fetchPage(query, 0);
                    this.mentionResults = response?.items || response || [];
                    this.mentionHasMore = response?.hasMore || false;
                    this.mentionIndex = 0;
                    this.mentionInitialLoading = false;
                    this.managePollingDocs();
                }, 150);
            },

            async loadMoreMentions() {
                if (this.mentionLoading || !this.mentionHasMore) return;
                this.mentionLoading = true;
                this.mentionPage++;
                const response = await this.fetchPage(this.mentionQuery, this.mentionPage);
                this.mentionResults = [...this.mentionResults, ...(response?.items || [])];
                this.mentionHasMore = response?.hasMore || false;
                this.mentionLoading = false;
            },

            handleDocFileInput(ev) {
                const f = ev.target.files?.[0];
                if (f) this.uploadDocument(f);
                ev.target.value = '';
            },

            handleDocDrop(ev) {
                const f = ev.dataTransfer?.files?.[0];
                if (f) this.uploadDocument(f);
            },

            async uploadDocument(file) {
                this.docUploadError = '';
                const allowed = ['pdf', 'docx', 'txt', 'md', 'csv'];
                const ext = (file.name.split('.').pop() || '').toLowerCase();
                if (!allowed.includes(ext)) {
                    this.docUploadError = 'Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.';
                    return;
                }
                if (file.size > 20 * 1024 * 1024) {
                    this.docUploadError = 'Arquivo maior que 20MB.';
                    return;
                }

                this.docUploading = true;
                try {
                    const fd = new FormData();
                    fd.append('file', file);
                    const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                    const res = await fetch('https://corestudio.ai/dashboard/user/chat/documents', {
                        method: 'POST',
                        headers: {
                            'X-CSRF-TOKEN': token,
                            'Accept': 'application/json',
                        },
                        body: fd,
                        credentials: 'same-origin',
                    });
                    if (!res.ok) {
                        const data = await res.json().catch(() => ({}));
                        this.docUploadError = data.message || 'Falha no upload.';
                    } else {
                        const data = await res.json();
                        const newItem = {
                            id: data.id,
                            source: 'rag_document',
                            type: 'document',
                            title: data.title,
                            meta: data.meta || 'Processando…',
                            status: data.status,
                            ready: false,
                        };
                        this.mentionResults = [newItem, ...this.mentionResults];
                        this.managePollingDocs();
                    }
                } catch (e) {
                    this.docUploadError = 'Erro de rede no upload.';
                } finally {
                    this.docUploading = false;
                }
            },

            managePollingDocs() {
                clearInterval(this.docPollTimer);
                this.docPollTimer = null;
                if (this.mentionActiveTab !== 'documents') return;
                const hasPending = this.mentionResults.some(r => r.ready === false || r.status === 'pending' || r.status === 'processing');
                if (!hasPending) return;
                this.docPollTimer = setInterval(async () => {
                    if (!this.mentionOpen || this.mentionActiveTab !== 'documents') {
                        clearInterval(this.docPollTimer);
                        this.docPollTimer = null;
                        return;
                    }
                    const response = await this.$wire.searchUserDocuments(this.mentionQuery, 0);
                    const items = response?.items || [];
                    this.mentionResults = items;
                    const stillPending = items.some(r => r.ready === false);
                    if (!stillPending) {
                        clearInterval(this.docPollTimer);
                        this.docPollTimer = null;
                    }
                }, 3000);
            },

            toggleMentionSelection(item) {
                const key = (item.source || 'config') + '_' + item.id;
                const idx = this.mentionSelected.findIndex(s => (s.source || 'config') + '_' + s.id === key);
                if (idx === -1) {
                    this.mentionSelected.push(item);
                } else {
                    this.mentionSelected.splice(idx, 1);
                }
            },

            isMentionSelected(item) {
                const key = (item.source || 'config') + '_' + item.id;
                return this.mentionSelected.some(s => (s.source || 'config') + '_' + s.id === key);
            },

            confirmMentionSelection() {
                if (!this.mentionSelected.length) return;
                const el = this.$refs.chatInput;
                const sel = window.getSelection();
                let range = null;

                if (sel.rangeCount && el.contains(sel.anchorNode)) {
                    range = sel.getRangeAt(0).cloneRange();
                    range.collapse(false);
                }

                this.mentionSelected.forEach(item => {
                    const tag = document.createElement('span');
                    tag.className = 'dc-mention-tag';
                    tag.contentEditable = 'false';
                    tag.dataset.refId = item.id;
                    tag.dataset.refSource = item.source || 'config';
                    tag.textContent = item.title;

                    if (range) {
                        range.insertNode(tag);
                        range.setStartAfter(tag);
                        range.collapse(true);
                        const space = document.createTextNode(' ');
                        range.insertNode(space);
                        range.setStartAfter(space);
                        range.collapse(true);
                    } else {
                        el.appendChild(tag);
                        el.appendChild(document.createTextNode(' '));
                    }

                    this.$wire.attachReference(item.id, item.source || 'config');
                });

                if (range) {
                    sel.removeAllRanges();
                    sel.addRange(range);
                }

                el.focus();
                this.syncQuestion();
                this.mentionSelected = [];
                this.mentionOpen = false;
                this.mentionResults = [];
            },

            selectMention(item) {
                const el = this.$refs.chatInput;

                // Criar tag inline no contenteditable
                const tag = document.createElement('span');
                tag.className = 'dc-mention-tag';
                tag.contentEditable = 'false';
                tag.dataset.refId = item.id;
                tag.dataset.refSource = item.source || 'config';
                tag.textContent = item.title;

                // Inserir tag na posição do cursor (ou no final)
                const sel = window.getSelection();
                let inserted = false;

                if (sel.rangeCount && el.contains(sel.anchorNode)) {
                    const range = sel.getRangeAt(0);
                    range.collapse(false);
                    range.insertNode(tag);
                    // Adicionar espaço após a tag
                    const space = document.createTextNode('\u00A0');
                    tag.after(space);
                    range.setStartAfter(space);
                    range.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    inserted = true;
                }

                if (!inserted) {
                    el.appendChild(tag);
                    el.appendChild(document.createTextNode('\u00A0'));
                }

                el.focus();
                this.$wire.attachReference(item.id, item.source || 'config');
                this.syncQuestion();

                this.mentionOpen = false;
                this.mentionResults = [];
            },

            handleTagDelete(e, direction) {
                const sel = window.getSelection();
                if (!sel.rangeCount || !sel.isCollapsed) return;

                const node = sel.anchorNode;
                const offset = sel.anchorOffset;
                let tagToRemove = null;

                if (direction === 'backspace') {
                    if (node.nodeType === Node.TEXT_NODE && offset === 0) {
                        const prev = node.previousSibling;
                        if (prev && prev.classList && prev.classList.contains('dc-mention-tag')) {
                            tagToRemove = prev;
                        }
                    } else if (node.nodeType === Node.ELEMENT_NODE && offset > 0) {
                        const prevChild = node.childNodes[offset - 1];
                        if (prevChild && prevChild.classList && prevChild.classList.contains('dc-mention-tag')) {
                            tagToRemove = prevChild;
                        }
                    }
                } else {
                    if (node.nodeType === Node.TEXT_NODE && offset === node.textContent.length) {
                        const next = node.nextSibling;
                        if (next && next.classList && next.classList.contains('dc-mention-tag')) {
                            tagToRemove = next;
                        }
                    } else if (node.nodeType === Node.ELEMENT_NODE && offset < node.childNodes.length) {
                        const nextChild = node.childNodes[offset];
                        if (nextChild && nextChild.classList && nextChild.classList.contains('dc-mention-tag')) {
                            tagToRemove = nextChild;
                        }
                    }
                }

                if (tagToRemove) {
                    e.preventDefault();
                    const refId = parseInt(tagToRemove.dataset.refId);
                    const refSource = tagToRemove.dataset.refSource || 'config';
                    tagToRemove.remove();
                    this.$wire.detachReference(refId, refSource);
                    this.syncQuestion();
                }
            },

            syncQuestion() {
                const el = this.$refs.chatInput;
                this.$wire.set('question', el.textContent || '');
            },

            toggleSpeech() {
                if (!this.speechSupported) return;
                if (this.isListening) { this.stopSpeech(); return; }
                this.startSpeech();
            },

            async startSpeech() {
                const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (!SR) return;

                // Capturar stream do microfone para o visualizador
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    this._audioStream = stream;
                    this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const source = this._audioCtx.createMediaStreamSource(stream);
                    const analyser = this._audioCtx.createAnalyser();
                    analyser.fftSize = 64;
                    analyser.smoothingTimeConstant = 0.7;
                    source.connect(analyser);
                    this._audioAnalyser = analyser;
                } catch (e) {
                    console.warn('[speech] mic stream falhou, visualizador desabilitado:', e.message);
                }

                const rec = new SR();
                rec.lang = 'pt-BR';
                rec.continuous = true;
                rec.interimResults = false;

                rec.onresult = (ev) => {
                    let finalText = '';
                    for (let i = ev.resultIndex; i < ev.results.length; i++) {
                        if (ev.results[i].isFinal) finalText += ev.results[i][0].transcript;
                    }
                    if (finalText) this.insertSpeechText(finalText);
                };
                rec.onerror = (ev) => {
                    console.warn('[speech] erro:', ev.error);
                    this.stopSpeech();
                };
                rec.onend = () => {
                    this.stopSpeech();
                };

                try {
                    rec.start();
                    this.speechRec   = rec;
                    this.isListening = true;
                    this.$refs.chatInput?.focus();
                    this._startWaveAnimation();
                } catch (e) {
                    console.warn('[speech] falha ao iniciar:', e);
                    this.stopSpeech();
                }
            },

            stopSpeech() {
                try { this.speechRec?.stop(); } catch (e) { /* noop */ }
                this._stopWaveAnimation();
                // Limpar stream do microfone
                if (this._audioStream) {
                    this._audioStream.getTracks().forEach(t => t.stop());
                    this._audioStream = null;
                }
                if (this._audioCtx) {
                    this._audioCtx.close().catch(() => {});
                    this._audioCtx = null;
                    this._audioAnalyser = null;
                }
                this.isListening = false;
                this.speechRec = null;
            },

            _startWaveAnimation() {
                const analyser = this._audioAnalyser;
                const wave = this.$refs.voiceWave;
                if (!wave) return;
                const bars = wave.querySelectorAll('.dc-voice-wave-bar');
                if (!bars.length) return;

                const bufferLength = analyser ? analyser.frequencyBinCount : 0;
                const dataArray = analyser ? new Uint8Array(bufferLength) : null;

                const draw = () => {
                    this._audioRaf = requestAnimationFrame(draw);
                    if (analyser && dataArray) {
                        analyser.getByteFrequencyData(dataArray);
                        const step = Math.max(1, Math.floor(bufferLength / bars.length));
                        bars.forEach((bar, i) => {
                            const val = dataArray[i * step] || 0;
                            const h = Math.max(4, (val / 255) * 28);
                            bar.style.height = h + 'px';
                        });
                    } else {
                        // Fallback: animação aleatória caso mic stream não disponível
                        bars.forEach(bar => {
                            bar.style.height = (4 + Math.random() * 20) + 'px';
                        });
                    }
                };
                draw();
            },

            _stopWaveAnimation() {
                if (this._audioRaf) {
                    cancelAnimationFrame(this._audioRaf);
                    this._audioRaf = null;
                }
                const wave = this.$refs.voiceWave;
                if (wave) {
                    wave.querySelectorAll('.dc-voice-wave-bar').forEach(bar => {
                        bar.style.height = '4px';
                    });
                }
            },

            insertSpeechText(text) {
                const el = this.$refs.chatInput;
                if (!el) return;

                const trimmed = text.trim();
                if (!trimmed) return;

                const sel = window.getSelection();
                const cursorInInput = sel.rangeCount && el.contains(sel.anchorNode);

                const needsSpaceBefore = el.textContent.length > 0
                    && !/\s$/.test(el.textContent);
                const chunk = (needsSpaceBefore ? ' ' : '') + trimmed + ' ';
                const node  = document.createTextNode(chunk);

                if (cursorInInput) {
                    const range = sel.getRangeAt(0);
                    range.collapse(false);
                    range.insertNode(node);
                    range.setStartAfter(node);
                    range.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(range);
                } else {
                    el.appendChild(node);
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    range.collapse(false);
                    sel.removeAllRanges();
                    sel.addRange(range);
                }

                this.syncQuestion();
            },

            removeTagFromInput(refId, refSource) {
                const el = this.$refs.chatInput;
                const tags = el.querySelectorAll('.dc-mention-tag');
                tags.forEach(tag => {
                    if (parseInt(tag.dataset.refId) === refId && (tag.dataset.refSource || 'config') === refSource) {
                        tag.remove();
                    }
                });
                this.syncQuestion();
            },

            getQuestionWithMarkers() {
                const el = this.$refs.chatInput;
                let result = '';
                const walk = (node) => {
                    if (node.nodeType === Node.TEXT_NODE) {
                        result += node.textContent;
                    } else if (node.classList && node.classList.contains('dc-mention-tag')) {
                        result += '@[' + node.textContent + ']';
                    } else {
                        node.childNodes.forEach(walk);
                    }
                };
                el.childNodes.forEach(walk);
                return result.trim();
            },

            formatUserMessage(content) {
                if (!content) return '';
                const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                return escaped.replace(/@\[([^\]]+)\]/g, '<span class="dc-mention-tag-display">$1</span>');
            },

            processActionButtons(html) {
                if (!html) return html;
                const titles = {
                    roteiro: 'Criar roteiro a partir desta headline',
                    roteiro_edit: 'Criar roteiro com headline editável',
                    select_reel: 'Usar este reel como base',
                };
                return html.replace(
                    /\{\{action:(\w+)\|([^}]+)\}\}/g,
                    (match, actionType, paramsStr) => {
                        const params = {};
                        paramsStr.split('|').forEach(pair => {
                            const eqIdx = pair.indexOf('=');
                            if (eqIdx > -1) {
                                params[pair.slice(0, eqIdx).trim()] = pair.slice(eqIdx + 1).trim();
                            }
                        });
                        const escaped = JSON.stringify(params).replace(/"/g, '&quot;');

                        // Botão de seleção de reel — estilo diferente (sem edit)
                        if (actionType === 'select_reel') {
                            return `<button class="dc-action-btn dc-action-btn-reel" data-action="select_reel" data-params="${escaped}" title="Usar este reel como base"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5l10 -10"/></svg></button>`;
                        }

                        const titleDirect = titles[actionType] || actionType;
                        const titleEdit = titles[actionType + '_edit'] || 'Editar e enviar';

                        const btnDirect = `<button class="dc-action-btn" data-action="${actionType}" data-params="${escaped}" title="${titleDirect}"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M15 10l4.553 -2.276a1 1 0 0 1 1.447 .894v6.764a1 1 0 0 1 -1.447 .894l-4.553 -2.276v-4z"/><path d="M3 6m0 2a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2z"/></svg></button>`;

                        const btnEdit = `<button class="dc-action-btn dc-action-btn-edit" data-action="${actionType}_edit" data-params="${escaped}" title="${titleEdit}"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/></svg></button>`;

                        return btnDirect + btnEdit;
                    }
                );
            },

            handleActionButton(action, params) {
                if (this.streaming) return;

                const actionAgentMap = {"headline_express":3,"roteiro":2,"headline":1};

                // Botão de editar: coloca texto no input para o usuário editar antes de enviar
                if (action.endsWith('_edit')) {
                    const baseAction = action.replace('_edit', '');
                    const agentId = actionAgentMap[baseAction] || null;

                    if (agentId) {
                        this.$wire.set('selectedAgentId', agentId);
                    }

                    const id = params.id || '';
                    const headline = params.headline || '';
                    const text = `Crie um roteiro para a headline: "${headline}" (estrutura_id: ${id})`;

                    this.$refs.chatInput.innerText = text;
                    this.$refs.chatInput.focus();
                    // Posicionar cursor no final
                    const range = document.createRange();
                    range.selectNodeContents(this.$refs.chatInput);
                    range.collapse(false);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    return;
                }

                // Botão direto: envia imediatamente
                const agentId = actionAgentMap[action] || null;

                if (agentId) {
                    this.$wire.set('selectedAgentId', agentId);
                }

                let question;
                if (action === 'roteiro') {
                    const id = params.id || '';
                    const headline = params.headline || '';
                    question = `Crie um roteiro para a headline: "${headline}" (estrutura_id: ${id})`;
                } else if (action === 'select_reel') {
                    const reel = params.reel || '1';
                    const caption = params.caption || '';
                    question = `Quero usar o reel ${reel}: "${caption}"`;
                } else {
                    question = `Execute ação ${action}: ${JSON.stringify(params)}`;
                }

                this.askViaSSE(question, agentId);
            },

            getReferencesFromDom() {
                const el = this.$refs.chatInput;
                const tags = el.querySelectorAll('.dc-mention-tag');
                const refs = [];
                const seen = new Set();
                tags.forEach(tag => {
                    const key = (tag.dataset.refSource || 'config') + '_' + tag.dataset.refId;
                    if (!seen.has(key)) {
                        seen.add(key);
                        refs.push({
                            source: tag.dataset.refSource || 'config',
                            id: parseInt(tag.dataset.refId),
                        });
                    }
                });
                return refs;
            },

            async askViaSSE(questionOverride = null, agentIdOverride = null) {
                // Ler conteúdo com marcadores @[titulo] para menções
                const question = questionOverride || this.getQuestionWithMarkers();
                const selectedAgentId = agentIdOverride || this.$wire.get('selectedAgentId');
                const conversationId = this.localConversationId || this.$wire.get('conversationId');

                if (!question || !selectedAgentId) return;

                // Extrair referências direto das tags DOM (mais confiável que $wire.attachedReferences)
                const attachedRefs = questionOverride ? [] : this.getReferencesFromDom();

                // Limpar input (apenas quando não é override de botão de ação)
                if (!questionOverride) {
                    this.$refs.chatInput.innerHTML = '';
                    this.$refs.chatInput.style.height = 'auto';
                }

                // Adicionar mensagem do user nas mensagens locais
                console.log('[MSG-DEBUG] Push user msg, localMessages count before:', this.localMessages.length);
                this.pushLocalMessage({ role: 'user', content: question });

                this.resetSteps();
                this.streamedText = '';
                this.streaming = true;

                const scrollArea = this.$refs.chatMessages;
                const scrollToEnd = (force = false) => {
                    if (!scrollArea) return;
                    // Durante o streaming só acompanha o bottom se o usuário ainda está lá.
                    // Se ele rolou pra cima, respeita a posição dele.
                    if (!force && !this.atBottom) return;
                    this.$nextTick(() => scrollArea.scrollTo({ top: scrollArea.scrollHeight }));
                };
                // Ao enviar uma nova pergunta, forçar volta ao bottom e religar o auto-scroll.
                this.atBottom = true;
                scrollToEnd(true);

                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
                const streamUrl = 'https://corestudio.ai/dashboard/user/chat/stream';

                try {
                    await window.fetchEventSource(streamUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': csrfToken,
                            'Accept': 'text/event-stream',
                        },
                        body: JSON.stringify({
                            question: question,
                            selected_agent_id: selectedAgentId,
                            conversation_id: conversationId,
                            attached_reference_ids: attachedRefs,
                        }),
                        openWhenHidden: true, // Manter conexão quando aba fica em background
                        onopen: async (response) => {
                            if (!response.ok) {
                                const body = await response.text().catch(() => '');
                                console.error('[SSE] onopen erro:', response.status, body);
                                throw new Error('Erro na conexão: ' + response.status);
                            }
                        },
                        onmessage: (event) => {
                            if (!event.data) return;
                            const data = JSON.parse(event.data);

                            switch (event.event) {
                                case 'token':
                                    this.streamedText += data.text;
                                    this.typingText = this.streamedText;
                                    // Renderizar markdown com debounce
                                    clearTimeout(this.renderTimer);
                                    this.renderTimer = setTimeout(() => {
                                        if (typeof marked !== 'undefined') {
                                            this.typingHtml = this.processActionButtons(marked.parse(this.streamedText));
                                        }
                                        scrollToEnd();
                                    }, 40);
                                    break;

                                case 'progress':
                                    if (!this.streamedText) {
                                        this.typingText = data.message || '';
                                    }
                                    break;

                                case 'rag_step': {
                                    const label = this.toolLabels[data.tool] ?? data.tool;
                                    if (data.status === 'start') {
                                        this.steps.push({ tool: data.tool, label, status: 'start', data: data.data || {} });
                                        this.stepsOpen = true;
                                    } else if (data.status === 'done') {
                                        const idx = this.steps.findLastIndex(s => s.tool === data.tool && s.status === 'start');
                                        if (idx !== -1) {
                                            this.steps[idx] = { ...this.steps[idx], status: 'done', data: { ...this.steps[idx].data, ...(data.data || {}) } };
                                        }
                                    }
                                    break;
                                }

                                case 'tool_start': {
                                    // Só adicionar se não existe um rag_step 'start' com o mesmo nome
                                    const existing = this.steps.findLastIndex(s => s.tool === data.name && s.status === 'start');
                                    if (existing === -1) {
                                        const label = this.toolLabels[data.name] ?? data.name;
                                        this.steps.push({ tool: data.name, label, status: 'start', data: {} });
                                        this.stepsOpen = true;
                                    }
                                    break;
                                }

                                case 'tool_end': {
                                    // Mesclar duration_ms com dados existentes (rag_step pode ter populado query, items, sources)
                                    const idx = this.steps.findLastIndex(s => s.tool === data.name);
                                    if (idx !== -1) {
                                        this.steps[idx] = {
                                            ...this.steps[idx],
                                            status: 'done',
                                            data: { ...this.steps[idx].data, duration_ms: data.duration_ms },
                                        };
                                    }
                                    break;
                                }

                                // ── Eventos de refinamento (streaming suprimido com revisores) ──
                                case 'refining_start': {
                                    this.steps.push({
                                        tool: 'refining',
                                        label: data.label + '...',
                                        kind: 'refining',
                                        status: 'start',
                                        data: {},
                                    });
                                    this.stepsOpen = true;
                                    break;
                                }

                                case 'refining_end': {
                                    const idx = this.steps.findLastIndex(s => s.tool === 'refining' && s.status === 'start');
                                    if (idx !== -1) {
                                        this.steps[idx] = { ...this.steps[idx], status: 'done' };
                                    }
                                    break;
                                }

                                // ── Eventos de revisão pós-geração ────────────────────────
                                case 'review_start': {
                                    const stepKey = `review:${data.reviewer_id}:${data.attempt}`;
                                    this.steps.push({
                                        tool: stepKey,
                                        label: `Analisando: ${data.reviewer_name}`,
                                        kind: 'review',
                                        status: 'start',
                                        data: {
                                            reviewer_id: data.reviewer_id,
                                            reviewer_name: data.reviewer_name,
                                            reviewer_description: data.reviewer_description || null,
                                            attempt: data.attempt,
                                            max_attempts: data.max_attempts,
                                        },
                                    });
                                    this.stepsOpen = true;
                                    break;
                                }

                                case 'review_end': {
                                    const prefix = `review:${data.reviewer_id}:`;
                                    const idx = this.steps.findLastIndex(s => typeof s.tool === 'string' && s.tool.startsWith(prefix) && s.status === 'start');
                                    if (idx !== -1) {
                                        this.steps[idx] = {
                                            ...this.steps[idx],
                                            status: data.approved ? 'approved' : 'rejected',
                                            label: data.approved
                                                ? `Aprovado: ${this.steps[idx].data.reviewer_name}`
                                                : `Reprovou: ${this.steps[idx].data.reviewer_name}`,
                                            data: {
                                                ...this.steps[idx].data,
                                                approved: data.approved,
                                                feedback: data.feedback || null,
                                                duration_ms: data.duration_ms,
                                                metadata: data.metadata || null,
                                            },
                                        };
                                    }
                                    break;
                                }

                                case 'review_retry': {
                                    this.steps.push({
                                        tool: `review:retry:${data.attempt}`,
                                        label: `Refazendo texto (tentativa ${data.attempt}/${data.max_attempts})`,
                                        kind: 'review_retry',
                                        status: 'start',
                                        data: {
                                            attempt: data.attempt,
                                            max_attempts: data.max_attempts,
                                            reason: data.reason || '',
                                        },
                                    });
                                    this.stepsOpen = true;
                                    // Limpar o texto streamado: a nova versão vai substituir.
                                    this.streamedText = '';
                                    this.typingHtml = '';
                                    break;
                                }

                                case 'review_warn': {
                                    this.steps.push({
                                        tool: `review:warn:${data.reviewer_id}`,
                                        label: `Aviso: ${data.reviewer_name}`,
                                        kind: 'review_warn',
                                        status: 'warn',
                                        data: {
                                            reviewer_id: data.reviewer_id,
                                            reviewer_name: data.reviewer_name,
                                            feedback: data.feedback || '',
                                        },
                                    });
                                    break;
                                }

                                case 'completed':
                                    this.stopTyping();
                                    this.streaming = false;
                                    console.log('[MSG-DEBUG] SSE completed, push assistant msg, localMessages count before:', this.localMessages.length);
                                    // Mover texto streamado para mensagens locais com HTML renderizado pelo backend
                                    this.pushLocalMessage({
                                        role: 'assistant',
                                        content: this.streamedText,
                                        html: this.processActionButtons(data.message_html || this.streamedText),
                                        id: data.message_id || null,
                                    });
                                    this.streamedText = '';
                                    // Guardar conversationId para próximas mensagens na mesma sessão
                                    this.localConversationId = data.conversation_id;
                                    // Atualizar URL com o conversation_id
                                    if (data.conversation_id) {
                                        const url = new URL(window.location);
                                        url.searchParams.set('c', data.conversation_id);
                                        window.history.replaceState({}, '', url);
                                    }
                                    scrollToEnd();
                                    break;

                                case 'error':
                                    this.stopTyping();
                                    this.streaming = false;
                                    console.log('[MSG-DEBUG] SSE error, push error msg, localMessages count before:', this.localMessages.length);
                                    this.pushLocalMessage({
                                        role: 'assistant',
                                        content: data.message || 'Erro ao processar.',
                                        html: data.message || 'Erro ao processar.',
                                    });
                                    this.streamedText = '';
                                    {
                                        const ri = this.steps.findLastIndex(s => s.tool === 'refining' && s.status === 'start');
                                        if (ri !== -1) this.steps[ri] = { ...this.steps[ri], status: 'rejected', label: 'Revisão bloqueada' };
                                    }
                                    break;
                            }
                        },
                        onerror: (err) => {
                            console.error('[SSE] onerror:', err);
                            this.stopTyping();
                            this.streaming = false;
                            this.pushLocalMessage({
                                role: 'assistant',
                                content: 'Conexão perdida. Tente novamente.',
                                html: 'Conexão perdida. Tente novamente.',
                            });
                            this.streamedText = '';
                            throw err;
                        },
                    });
                } catch (e) {
                    if (this.streaming) {
                        this.stopTyping();
                        this.streaming = false;
                        this.streamedText = '';
                    }
                }
            },

            startTyping() {
                this.typingIndex = 0;
                this.typingText  = this.typingPhrases[0] + '...';
                this.typingTimer = setInterval(() => {
                    this.typingIndex = (this.typingIndex + 1) % this.typingPhrases.length;
                    this.typingText  = this.typingPhrases[this.typingIndex] + '...';
                }, 3000);
            },

            stopTyping() {
                clearInterval(this.typingTimer);
                clearTimeout(this.renderTimer);
                this.typingTimer = null;
                this.typingText  = '';
                this.typingHtml  = '';
            },

            resetSteps() {
                this.steps     = [];
                this.stepsOpen = true;
                this.startTyping();
            },

            openTrace(trace) {
                this.traceData = trace || {};
                this.traceVisible = true;
                this.loadingTraceId = null;
            },

            closeTrace() {
                this.traceVisible = false;
                this.traceData = {};
            },

            async loadToolDetail(detailsEl, roundIndex, toolIndex) {
                const contentEl = detailsEl.querySelector('.dc-tool-detail');
                if (!contentEl) return;

                contentEl.textContent = 'Carregando detalhes...';
                contentEl.style.cssText = 'color:#8b949e; font-size:.72rem; padding:8px;';

                try {
                    const html = await this.$wire.loadToolDetail(this.traceData._messageId, roundIndex, toolIndex);
                    if (html) {
                        contentEl.style.cssText = '';
                        contentEl.innerHTML = html;
                    } else {
                        contentEl.textContent = 'Sem dados';
                        contentEl.style.cssText = 'color:#f85149; padding:8px;';
                    }
                    const rounds = this.traceData.rounds || [];
                    if (rounds[roundIndex]?.tool_calls?.[toolIndex]) {
                        rounds[roundIndex].tool_calls[toolIndex]._loaded = true;
                    }
                } catch (e) {
                    contentEl.textContent = 'Erro ao carregar: ' + e.message;
                    contentEl.style.cssText = 'color:#f85149; padding:8px;';
                }
            },

            formatTraceDuration(ms) {
                if (!ms) return '-';
                return ms > 1000 ? (ms / 1000).toFixed(1) + 's' : ms + 'ms';
            },

            formatTraceTokens() {
                if (!this.traceData.usage) return '-';
                const u = this.traceData.usage;
                const prompt = u.prompt_tokens || 0;
                const completion = u.completion_tokens || 0;
                const total = u.total_tokens || (prompt + completion);
                return 'in: ' + prompt.toLocaleString() + ' · out: ' + completion.toLocaleString() + ' · total: ' + total.toLocaleString();
            },

            tryParseJson(val) {
                if (val === null || val === undefined) return null;
                if (typeof val === 'object') return val;
                if (typeof val !== 'string') return val;
                try { return JSON.parse(val); } catch (e) { return val; }
            },

            renderJsonTree(data, depth = 0, expanded = false) {
                const h = (tag, cls, content) => '\x3c' + tag + (cls ? ' class="' + cls + '"' : '') + '\x3e' + content + '\x3c/' + tag + '\x3e';
                const hOpen = (tag, cls, attrs) => '\x3c' + tag + (cls ? ' class="' + cls + '"' : '') + (attrs || '') + '\x3e';
                const hClose = (tag) => '\x3c/' + tag + '\x3e';

                if (data === null || data === undefined) return h('span', 'jt-null', 'null');
                if (typeof data === 'boolean') return h('span', 'jt-bool', data);
                if (typeof data === 'number') return h('span', 'jt-num', data);
                if (typeof data === 'string') {
                    if (data.length > 300) {
                        const id = 'jt-' + Math.random().toString(36).substr(2, 9);
                        return h('span', 'jt-str', '"' + hOpen('span', '', ' id="'+id+'-short"') + this.escHtml(data.substring(0, 150)) + hOpen('button', 'jt-expand-str', ' onclick="document.getElementById(\''+id+'-short\').style.display=\'none\';document.getElementById(\''+id+'-full\').style.display=\'inline\';"') + '...+' + (data.length - 150) + ' chars' + hClose('button') + hClose('span') + hOpen('span', '', ' id="'+id+'-full" style="display:none"') + this.escHtml(data) + hClose('span') + '"');
                    }
                    return h('span', 'jt-str', '"' + this.escHtml(data) + '"');
                }
                if (Array.isArray(data)) {
                    if (data.length === 0) return h('span', 'jt-bracket', '[]');
                    const openAttr = expanded && depth < 2 ? ' open' : '';
                    let items = data.map((item, i) => {
                        const comma = i < data.length - 1 ? h('span', 'jt-comma', ',') : '';
                        return h('div', 'jt-row', this.renderJsonTree(item, depth + 1, expanded) + comma);
                    }).join('');
                    return hOpen('details', 'jt-details', openAttr) + hOpen('summary', 'jt-summary', '') + h('span', 'jt-bracket', '[') + h('span', 'jt-preview', data.length + ' items') + h('span', 'jt-bracket', ']') + hClose('summary') + h('div', 'jt-indent', items) + h('span', 'jt-bracket', ']') + hClose('details');
                }
                if (typeof data === 'object') {
                    const keys = Object.keys(data);
                    if (keys.length === 0) return h('span', 'jt-bracket', '{}');
                    const openAttr = expanded && depth < 2 ? ' open' : '';
                    let rows = keys.map((key, i) => {
                        const comma = i < keys.length - 1 ? h('span', 'jt-comma', ',') : '';
                        return h('div', 'jt-row', h('span', 'jt-key', '"' + this.escHtml(key) + '"') + h('span', 'jt-colon', ': ') + this.renderJsonTree(data[key], depth + 1, expanded) + comma);
                    }).join('');
                    const preview = keys.slice(0, 3).join(', ') + (keys.length > 3 ? ', ...' : '');
                    return hOpen('details', 'jt-details', openAttr) + hOpen('summary', 'jt-summary', '') + h('span', 'jt-bracket', '{') + h('span', 'jt-preview', this.escHtml(preview)) + h('span', 'jt-bracket', '}') + hClose('summary') + h('div', 'jt-indent', rows) + h('span', 'jt-bracket', '}') + hClose('details');
                }
                return h('span', '', this.escHtml(String(data)));
            },

            escHtml(str) {
                return String(str).replace(/&/g,'\x26amp;').replace(/</g,'\x26lt;').replace(/>/g,'\x26gt;');
            },

            ragStepLabel(tool) {
                return this.toolLabels[tool] ?? tool;
            },

            toolNameLabel(name) {
                const map = {
                    'consultar_nucleo_influencia_tool': 'Consultando perfil do cliente',
                    'consultar_gatilhos_tool': 'Estudando gatilhos de atencao',
                    'buscar_estruturas_tool': 'Buscando estruturas de headlines',
                    'consultar_pesquisa_viral_tool': 'Consultando pesquisa viral',
                    'consultar_variaveis_perfil_tool': 'Consultando variaveis do perfil',
                    'consultar_estruturas_perfil_tool': 'Consultando estruturas do perfil',
                    'gerar_headlines_tool': 'Gerando headlines',
                    'qualificar_headline_tool': 'Qualificando headline (QA)',
                    'criar_headline_tool': 'Criando headline',
                    'estruturar_roteiro_tool': 'Estruturando roteiro',
                    'avaliar_qualidade_conteudo_tool': 'Avaliando qualidade do conteudo',
                    'search_documents_tool': 'Buscando nos documentos',
                    'list_documents_tool': 'Listando documentos',
                    'search_web_tool': 'Buscando na web',
                    'salvar_memoria_tool': 'Salvando na memória',
                    'esquecer_memoria_tool': 'Apagando da memória',
                };
                return map[name] ?? name.replace(/_tool$/, '').replace(/_/g, ' ');
            },
        };
    }

    document.addEventListener('livewire:request', (e) => {
        if (e.detail?.payload?.calls?.some(c => c.method === 'ask')) {
            const el = document.querySelector('[x-data^="ragChat"]');
            if (el?._x_dataStack?.[0]?.resetSteps) {
                el._x_dataStack[0].resetSteps();
            }
        }
    });

    document.addEventListener('livewire:updated', () => {
        const el = document.getElementById('chat-messages');
        if (!el) return;
        const isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < 80;
        if (isAtBottom) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
    