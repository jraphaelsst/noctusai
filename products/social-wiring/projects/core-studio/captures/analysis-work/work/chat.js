/* ===== SCRIPT #1 @2821 attrs= len=794 */

        (function() {
            // ✅ V2 SEMPRE USA TEMA DARK (forçado como padrão)
            // CÓDIGO ANTERIOR (comentado - respeitava localStorage):
            // const theme = localStorage.getItem('tablerTheme');
            // if (!theme) {
            //     localStorage.setItem('tablerTheme', 'dark');
            //     document.documentElement.classList.add('theme-dark');
            // } else if (theme === 'dark') {
            //     document.documentElement.classList.add('theme-dark');
            // }

            // NOVO CÓDIGO: Força dark sempre na v2
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
        })();
    
/* ===== SCRIPT #3 @3763 attrs= len=469 */

        // ✅ V2 SEMPRE USA TEMA DARK (forçado após demo-theme.min.js)
        // Garante que o dark seja aplicado mesmo se o demo-theme.min.js tentar aplicar light
        (function() {
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            document.body.setAttribute('data-bs-theme', 'dark');
        })();
    
/* ===== SCRIPT #4 @35553 attrs= len=232 */

    const btn = document.querySelector('#btnShowMenuV2');
    const menuDropdown = document.querySelector('.dropdownMenuProfileV2');

    btn.addEventListener('click', () => {
        menuDropdown.classList.toggle('upV2');
    });

/* ===== SCRIPT #5 @51086 attrs= len=3598 */

function creditsBadge() {
    return {
        balance: null,

        init() {
            this.fetch();
            setInterval(() => this.fetch(), 30000);
        },

        async fetch() {
            try {
                const res = await fetch('https://corestudio.ai/dashboard/user/twin/api/credits', {
                    headers: { Accept: 'application/json' },
                });

                if (!res.ok) return;

                const json = await res.json();
                this.balance = json.balance;
                this.$el.classList.toggle('is-empty', json.balance < json.cost_per_minute);
            } catch (e) {
                console.error('[CreditsBadge] Erro ao buscar saldo:', e);
            }
        },
    };
}

function notificationsDropdown() {
    return {
        open: false,
        showRead: false,
        notifications: [],
        unreadCount: 0,
        readCount: 0,

        init() {
            this.fetch();
            setInterval(() => this.fetch(), 30000);
        },

        toggle() {
            this.open = !this.open;
            if (this.open) this.fetch();
        },

        toggleShowRead() {
            this.showRead = !this.showRead;
            this.fetch();
        },

        async fetch() {
            try {
                const url = new URL('https://corestudio.ai/dashboard/user/notifications', window.location.origin);
                if (this.showRead) url.searchParams.set('show_read', '1');
                const res = await fetch(url, {
                    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await res.json();
                this.notifications = data.notifications;
                this.unreadCount = data.unread_count;
                this.readCount = data.read_count;
            } catch (e) {
                console.error('[Notifications] Erro ao buscar:', e);
            }
        },

        async markRead(n) {
            if (n.status === 1) return;
            n.status = 1;
            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.readCount++;
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            await fetch(`/dashboard/user/notifications/${n.id}/read`, {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': token, 'Accept': 'application/json' }
            });
        },

        async markAllRead() {
            this.readCount += this.notifications.filter(n => n.status === 0).length;
            this.notifications = this.showRead
                ? this.notifications.map(n => ({ ...n, status: 1 }))
                : [];
            this.unreadCount = 0;
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            await fetch('https://corestudio.ai/dashboard/user/notifications/read-all', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': token, 'Accept': 'application/json' }
            });
        },

        timeAgo(dateStr) {
            const now = new Date();
            const date = new Date(dateStr);
            const diff = Math.floor((now - date) / 1000);
            if (diff < 60) return 'agora';
            if (diff < 3600) return Math.floor(diff / 60) + ' min atrás';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h atrás';
            if (diff < 604800) return Math.floor(diff / 86400) + 'd atrás';
            return date.toLocaleDateString('pt-BR');
        }
    }
}

/* ===== SCRIPT #6 @85979 attrs=type="application/json" id="ragchat-init-data" len=2825 */
{"conversations":[{"id":"01a10d2a-2e28-7197-a8c2-6b572a00d246","title":"vou te mandar um roteiro que quero que vc analise a estrutura pq ele viralizou muito e eu quero que ","updated_at":"2026-10-05 15:39:21"},{"id":"01a10846-e19f-7132-a001-4dfc8edac5c8","title":"hoje \u00e9 o primeiro turno das elei\u00e7\u00f5es 2026. podemos fazer um roteiro sobre isso de alguma forma pro g","updated_at":"2026-10-04 20:47:43"},{"id":"01a10860-5315-7255-8c8b-cd0e52f54e7a","title":"para a m\u00f4nica tangerino, em psicanalise (n\u00e3o falar sobre imoveis)\nLeve em considera\u00e7\u00e3o:\n\"Sentir al\u00edv","updated_at":"2026-10-04 16:25:22"},{"id":"01a10827-48c2-712a-82d2-3efa8a8e962f","title":"eu tenho alguns v\u00e1rios v\u00eddeos que foram mto bem no instagram. posso te mandar o roteiro pra vc fazer","updated_at":"2026-10-04 15:53:08"},{"id":"01a10813-e9c4-70d0-addf-4e6c4726c822","title":"O governo bateu o martelo. Agora voc\u00ea pode colocar a casa no seu nomemesmo sem ter os pap\u00e9is dela. E","updated_at":"2026-10-04 15:01:59"},{"id":"01a107ed-cf54-73ec-a4a3-a8a962148456","title":"PRIMEIRA SUGEST\u00c3O DE REEL - SOBRE CLAUSULA CONTRATUAL                                               ","updated_at":"2026-10-04 14:43:08"},{"id":"01a107cb-4ae7-737d-899b-a1e61e3bbb24","title":"Quando for comprar seu primeiro im\u00f3vel, n\u00e3o pergunte o pre\u00e7o primeiro.Pergunte isso. Porque o pre\u00e7o ","updated_at":"2026-10-04 14:17:24"},{"id":"01a1077f-0476-739d-8185-2cd869642066","title":"ROTEIROS GILSON - MODELADOS","updated_at":"2026-10-04 13:38:03"},{"id":"01a10795-336f-73af-9a3a-abddbdae2e82","title":"ROTEIROS MONICA","updated_at":"2026-10-04 12:54:18"},{"id":"01a10416-00d9-7092-ae75-a0d1206fdfd8","title":"ROTEIROS MONICA 2","updated_at":"2026-10-04 12:41:24"},{"id":"01a0f3dc-70db-73d8-9cfe-7b69cba44a42","title":"O QUARTO CHEIO DE MENINOS*Teve uma \u00e9poca em que parecia que a casa nunca ficava vazia.Tinha menino e","updated_at":"2026-10-02 18:44:50"},{"id":"01a0f2e5-3401-722c-a037-d3a510c2d8c5","title":"Bora escrever um roteiro pro Gilson sobre o poder do h\u00e1bito? Quero um reels de no max 90s, com o tem","updated_at":"2026-09-30 16:07:12"},{"id":"01a0df72-a658-71f7-97a0-5df36fca740e","title":"fa\u00e7a uma headline deste roteiro usando  @[@veridiana_cavalheri - Todos os v\u00eddeos] @[@elias.maman - T","updated_at":"2026-09-30 16:03:28"},{"id":"01a0df70-80a4-73fe-a63b-2f011b05e151","title":"S\u00f3 dentro desse chat, n\u00e3o use o seu conhecimento base sobre o Gilson","updated_at":"2026-09-26 17:39:28"},{"id":"01a0db45-c2ab-738e-aae8-45d5ff0ba679","title":"Crie uma headline sobre a import\u00e2ncia da localiza\u00e7\u00e3o na escolha de um im\u00f3vel.","updated_at":"2026-09-25 22:13:05"}],"actionAgentMap":{"headline_express":3,"roteiro":2,"headline":1},"roteiroAgentId":2}
/* ===== SCRIPT #8 @368669 attrs= len=67928 */

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
    
/* ===== SCRIPT #17 @445822 attrs= len=1020 */

    $.ajaxSetup({
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        }
    });

    // Interceptador global para erros de CSRF
    $(document).ajaxError(function(event, jqXHR, settings, thrownError) {
        if (jqXHR.status === 419 || // Laravel CSRF token expirado
            (jqXHR.responseJSON && 
            jqXHR.responseJSON.message && 
            jqXHR.responseJSON.message.toLowerCase().includes('csrf'))) {
            
            toastr.error('Sua sessão expirou. A página será recarregada.');
            
            // Recarrega a página após 2 segundos
            setTimeout(function() {
                window.location.reload();
            }, 2000);
        }
    });

    // Adiciona interceptador para renovar token CSRF periodicamente
    setInterval(function() {
        $.get('/csrf-token', function(data) {
            $('meta[name="csrf-token"]').attr('content', data.token);
        });
    }, 30 * 60 * 1000); // Renova a cada 30 minutos

/* ===== SCRIPT #19 @446956 attrs= len=2677 */

        $('form#customers-workspace-create').submit(function(e) {
            "use strict";

            e.preventDefault();

            const getPath = () => location.pathname.startsWith('/dashboard/admin/team') ?
                "/dashboard/admin/team" :
                "/dashboard/admin/customers";

            const baseUrl = window.location.origin;


            $('#create_workspace').prop('disabled', true);
            $('#create_workspace').text('Aguarde criando...');

            var formData = new FormData(this);

            $.ajax({
                type: "post",
                url: baseUrl + getPath() + "/workspace/create",
                data: formData,
                contentType: false,
                processData: false,
                success: function(data) {
                    toastr[data.type](data.message);

                    if (data.refresh) {
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    }
                },
                error: function(data) {
                    // Trata apenas erros não relacionados ao CSRF
                    if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message
                            .toLowerCase().includes('csrf'))) {
                        if (data.responseJSON && (data.responseJSON.error || data.responseJSON
                                .errors)) {
                            if (data.responseJSON.errors) {
                                var errors = data.responseJSON.errors;
                                $.each(errors, function(index, value) {
                                    toastr.error(value);
                                });
                            } else {
                                toastr.error(data.responseJSON.message);
                            }
                        } else {
                            toastr.error('Ocorreu um erro ao atualizar o cliente.');
                        }
                    }

                    $('#create_workspace').prop('disabled', false);
                    $('#create_workspace').html(
                        '<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-plus"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14" /><path d="M5 12l14 0" /></svg>Criar'
                    );
                }
            });
            return false;
        })
    
/* ===== SCRIPT #21 @449726 attrs= len=605 */

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;

    // Removido os eventos jQuery que controlavam a visibilidade dos botões
    // Agora isso é controlado pelo Alpine.js de forma reativa

    // Evento de clique no microfone agora é controlado pelo Alpine
    // $('.microphone-chat').click(function(){
    //     $('.audio-area-chat').removeClass('hidden');
    //     $('.input-message').addClass('hidden');
    //     $('.sendText').addClass('hidden');
    //     $('.microphone-chat').addClass('hidden');
    //     $("#record-button-chat").click();
    // });


/* ===== SCRIPT #22 @450350 attrs= len=9045 */

    let chatRecording = {
        isRecording: false,
        timer: null,
        seconds: 0,
        mediaRecorder: null,
        audioChunks: [],
        audioBlob: null,
        audioContext: null,
        analyser: null,
        dataArray: null
    };

    // Insere ícones SVG
    $(".icon-microphone-chat").html(`<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-microphone"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M19 9a1 1 0 0 1 1 1a8 8 0 0 1 -6.999 7.938l-.001 2.062h3a1 1 0 0 1 0 2h-8a1 1 0 0 1 0 -2h3v-2.062a8 8 0 0 1 -7 -7.938a1 1 0 1 1 2 0a6 6 0 0 0 12 0a1 1 0 0 1 1 -1m-7 -8a4 4 0 0 1 4 4v5a4 4 0 1 1 -8 0v-5a4 4 0 0 1 4 -4" /></svg>`);
    $(".icon-pause-chat").html(`<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-player-pause"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 4h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h2a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2z" /><path d="M17 4h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h2a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2z" /></svg>`);
    $(".icon-trash-chat").html(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-trash"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 7l16 0" /><path d="M10 11l0 6" /><path d="M14 11l0 6" /><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" /><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" /></svg>`);

    // Configura canvas
    function setupChatCanvas(canvas) {
        const scale = window.devicePixelRatio || 1;
        canvas.width = canvas.offsetWidth * scale;
        canvas.height = canvas.offsetHeight * scale;
        canvas.getContext("2d").scale(scale, scale);
    }

    // Clique no botão de gravação
    $("#record-button-chat").click(async () => {
        const canvas = document.getElementById("waveform-chat");
        const micIcon = $("#record-button-chat .mic-icon");
        const micPause = $("#record-button-chat .mic-pause");
        const timerEl = $("#record-timer-chat");
        const divAudio = $(".div-audio-chat");
        const divControls = $(".div-controls-chat");
        const player = $("#audio-player-chat");

        setupChatCanvas(canvas);

        if (!chatRecording.isRecording) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                chatRecording.audioContext = new AudioContext();
                chatRecording.analyser = chatRecording.audioContext.createAnalyser();
                chatRecording.analyser.fftSize = 256;
                chatRecording.dataArray = new Uint8Array(chatRecording.analyser.frequencyBinCount);
                const source = chatRecording.audioContext.createMediaStreamSource(stream);
                source.connect(chatRecording.analyser);

                chatRecording.mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm'
                });
                chatRecording.audioChunks = [];
                chatRecording.mediaRecorder.ondataavailable = e => chatRecording.audioChunks.push(e.data);
                chatRecording.mediaRecorder.start();

                chatRecording.seconds = 0;
                timerEl.text("00:00");
                chatRecording.timer = setInterval(() => {
                    chatRecording.seconds++;
                    timerEl.text(new Date(chatRecording.seconds * 1000).toISOString().substr(14, 5));
                }, 1000);

                micIcon.addClass("hidden");
                micPause.removeClass("hidden");
                chatRecording.isRecording = true;

                // animação canvas
                const ctx = canvas.getContext("2d");
                function draw() {
                    if (!chatRecording.isRecording) return;
                    chatRecording.analyser.getByteFrequencyData(chatRecording.dataArray);
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    let x = 0;
                    const barCount = 120;
                    const barWidth = Math.floor(canvas.width / barCount) - 2;
                    for (let i = 0; i < barCount; i++) {
                        const index = Math.floor((i / barCount) * chatRecording.dataArray.length);
                        const height = (chatRecording.dataArray[index] / 255) * canvas.height * 0.8;
                        ctx.fillStyle = "#00BFFF";
                        ctx.fillRect(x, (canvas.height - height) / 2, barWidth, height);
                        x += barWidth + 2;
                    }
                    requestAnimationFrame(draw);
                }
                draw();
            } catch (error) {
                alert("Erro ao acessar o microfone.");
                console.error(error);
            }
        } else {
            // Parar
            chatRecording.isRecording = false;
            micIcon.removeClass("hidden");
            micPause.addClass("hidden");
            clearInterval(chatRecording.timer);
            chatRecording.mediaRecorder.stop();

            chatRecording.mediaRecorder.onstop = () => {
                console.log('MediaRecorder parou');
                console.log('Audio chunks:', chatRecording.audioChunks.length);

                chatRecording.audioBlob = new Blob(chatRecording.audioChunks, { type: 'audio/webm' });
                console.log('Audio blob criado:', !!chatRecording.audioBlob);

                const url = URL.createObjectURL(chatRecording.audioBlob);
                console.log('URL criada:', url);

                player.attr("src", url);
                divAudio.addClass("hidden");
                divControls.removeClass("hidden");

                player[0].onloadedmetadata = () => {
                    if (player[0].duration === Infinity) {
                        player[0].currentTime = 1e101;
                        player[0].ontimeupdate = () => {
                            player[0].ontimeupdate = null;
                            player[0].currentTime = 0; // volta ao início
                        };
                    }
                };


                // Atualizar o estado do Alpine
                const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
                if (alpineComponent) {
                    // Forçar atualização do estado
                    alpineComponent.$data.audioUrl = url;
                    alpineComponent.$data.audioBlob = chatRecording.audioBlob;
                    alpineComponent.$data.isLoading = false;

                    // Debug
                    console.log('Audio Blob definido no Alpine:', !!alpineComponent.$data.audioBlob);
                    console.log('Audio URL definido no Alpine:', !!alpineComponent.$data.audioUrl);
                }

                // Garantir que chatRecording está acessível globalmente
                window.chatRecording = chatRecording;
                console.log('chatRecording definido globalmente:', !!window.chatRecording);
                console.log('chatRecording.audioBlob global:', !!window.chatRecording.audioBlob);
            };
        }
    });

    // Botão de apagar - agora controlado pelo Alpine.js
    // $("#delete-button-chat").click(() => {
    //     // Usar o Alpine.js para resetar os controles
    //     const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
    //     if (alpineComponent) {
    //         alpineComponent.switchToText();
    //     }
    //
    //     // Resetar elementos específicos do áudio
    //     $(".div-controls-chat").addClass("hidden");
    //     $(".div-audio-chat").removeClass("hidden");
    //     $("#record-timer-chat").text("00:00");
    //     $("#audio-player-chat").attr("src", "");

    //     // Resetar variáveis do chatRecording
    //     chatRecording = {
    //         isRecording: false,
    //         timer: null,
    //         seconds: 0,
    //         mediaRecorder: null,
    //         audioChunks: [],
    //         audioBlob: null,
    //         audioContext: null,
    //         analyser: null,
    //         dataArray: null
    //     };
    // });

    // Adicionar evento de clique no botão de enviar áudio
    $('.sendAudio').on('click', function() {
        const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
        if (alpineComponent && chatRecording.audioBlob) {
            // Garantir que o audioBlob está definido antes de chamar sendMessage
            alpineComponent.$data.audioBlob = chatRecording.audioBlob;
            alpineComponent.$data.audioUrl = URL.createObjectURL(chatRecording.audioBlob);
            alpineComponent.sendMessage();
        }
    });


/* ===== SCRIPT #23 @459422 attrs= len=1554 */

            $(document).ready(function() {
                const $dropdowns = $('.navDropdownV2');
                const $navLinks = $('.navLinkV2');
                const $dropdownBoxes = $('.asideDropdownItemV2');

                $dropdowns.on('click', function() {
                    // Remove estados ativos
                    // $dropdowns.removeClass('active');
                    // $navLinks.removeClass('active');
                    $dropdownBoxes.removeClass('d-block');

                    // Ativa o dropdown atual
                    const $current = $(this);
                    // $current.addClass('active');
                    $current.find('.asideDropdownItemV2').addClass('d-block');
                });

                $('.subMenuTriggerV2').on('click', function(e) {
                    e.stopPropagation();
                    $(this).closest('.subMenuV2').toggleClass('open');
                });

                const containerBodyAsideV2 = $(".containerBodyAsideV2")
                $('#toggleSidebarButtonV2').on('click', function() {
                    containerBodyAsideV2.slideToggle(300);
                })

                $(window).on('resize', function(e) {
                    if (window.innerWidth > 990) {
                        containerBodyAsideV2.show()
                        containerBodyAsideV2.css("display", "flex")
                    } else {
                        containerBodyAsideV2.hide()
                    }
                });

                
                            })
        
/* ===== SCRIPT #24 @464938 attrs= len=1479 */

        document.addEventListener('DOMContentLoaded', function() {
            var modalEl = document.getElementById('modal-first-access-tutorial');
            if (!modalEl) return;

            // O backdrop do Bootstrap é anexado ao body, fora do modal — a classe no body
            // limita o escurecimento/blur a este modal e preserva os demais da plataforma.
            modalEl.addEventListener('show.bs.modal', function() {
                document.body.classList.add('first-access-modal-open');
            });
            modalEl.addEventListener('hidden.bs.modal', function() {
                document.body.classList.remove('first-access-modal-open');
            });

            
            function markFirstAccessSeen() {
                var token = document.querySelector('meta[name="csrf-token"]');
                if (!token) return;
                fetch('https://corestudio.ai/dashboard/user/first-access-seen', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': token.getAttribute('content'), 'Accept': 'application/json' },
                    body: '{}'
                }).catch(function() {});
            }

            document.getElementById('btn-first-access-trainings').addEventListener('click', markFirstAccessSeen, { once: true });
            document.getElementById('btn-first-access-skip').addEventListener('click', markFirstAccessSeen, { once: true });
        });
    
/* ===== SCRIPT #25 @466440 attrs=data-navigate-once="true" len=137 */
window.livewireScriptConfig = {"csrf":"HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC","uri":"\/livewire\/update","progressBar":"","nonce":""};
/* ===== SCRIPT #29 @466861 attrs= len=4402 */

            (function configureEcho() {
                if (window.Echo && window.Echo.__advancedRoadmapConfigured) {
                    console.warn('[Echo] Já inicializado anteriormente, ignorando nova configuração.');
                    window.dispatchEvent(new CustomEvent('echo:ready'));
                    return;
                }

                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                const userId = document.querySelector('meta[name="user-id"]')?.getAttribute('content');
                const env = document.querySelector('meta[name="app-env"]')?.getAttribute('content') || 'local';

                const pusherKey = "75830eeb9f5ab6e769a8";
                const pusherCluster = "us2";
                const configuredHost = "api-us2.pusher.com";
                const configuredPort = "443";
                const forceTLS = true;

                const isCustomHost = configuredHost && !configuredHost.startsWith('api-');
                const wsHost = isCustomHost ? configuredHost : null;
                const wsPort = isCustomHost && configuredPort ? Number(configuredPort) : null;
                const wssPort = isCustomHost && configuredPort ? Number(configuredPort) : null;

                if (!pusherKey || pusherKey === 'null') {
                    console.error('[AdvancedRoadmapChat] Pusher key não configurado. Verifique broadcasting.php.');
                    return;
                }

                console.info('[AdvancedRoadmapChat] Bootstrap do Echo', {
                    pusherKey,
                    pusherCluster,
                    wsHost,
                    wsPort,
                    wssPort,
                    forceTLS,
                    env,
                    userId,
                });

                const echoOptions = {
                    broadcaster: 'pusher',
                    key: pusherKey,
                    cluster: pusherCluster,
                    forceTLS: forceTLS,
                    enabledTransports: ['ws', 'wss'],
                    disableStats: true,
                    encrypted: forceTLS,
                    authEndpoint: '/broadcasting/auth',
                    auth: {
                        headers: {
                            'X-CSRF-TOKEN': csrfToken,
                        },
                    },
                };

                if (wsHost) {
                    echoOptions.wsHost = wsHost;
                }
                if (wsPort) {
                    echoOptions.wsPort = wsPort;
                }
                if (wssPort) {
                    echoOptions.wssPort = wssPort;
                }

                window.Echo = new Echo(echoOptions);
                window.Echo.__advancedRoadmapConfigured = true;
                window.dispatchEvent(new CustomEvent('echo:ready'));

                const pusher = window.Echo.connector?.pusher;
                if (!pusher) {
                    console.error('[AdvancedRoadmapChat] Falha ao obter instância do Pusher via Echo.');
                    return;
                }

                pusher.connection.bind('connecting', () => console.debug('[Echo] Conectando...'));
                pusher.connection.bind('connected', () => console.info('[Echo] Conectado com sucesso.'));
                pusher.connection.bind('disconnected', () => console.warn('[Echo] Desconectado.'));
                pusher.connection.bind('unavailable', () => console.warn('[Echo] Servidor indisponível.'));
                pusher.connection.bind('failed', () => console.error('[Echo] Conexão falhou.'));
                pusher.connection.bind('error', (error) => console.error('[Echo] Erro na conexão Pusher', error));

                if (console && console.debug) {
                    pusher.bind_global((eventName, data) => {
                        console.debug('[Echo] Evento global recebido', eventName, data);
                    });
                }

                window.addEventListener('beforeunload', () => {
                    try {
                        window.Echo.disconnect();
                        console.debug('[Echo] Conexão encerrada (beforeunload).');
                    } catch (error) {
                        console.error('[Echo] Erro ao desconectar', error);
                    }
                });
            })();
        
/* ===== SCRIPT #32 @471504 attrs=type="text/javascript" len=572 */

        window.$crisp = [];
        window.CRISP_WEBSITE_ID = "75cc752d-b49d-4b10-9a51-aeb70cf165c3";
                    // Nas telas de chat o balão do Crisp cobre o botão de enviar
            // e o clique sem querer fazia o usuário perder o que escreveu.
            window.$crisp.push(["do", "chat:hide"]);
                (function() {
            d = document;
            s = d.createElement("script");
            s.src = "https://client.crisp.chat/l.js";
            s.async = 1;
            d.getElementsByTagName("head")[0].appendChild(s);
        })();
    