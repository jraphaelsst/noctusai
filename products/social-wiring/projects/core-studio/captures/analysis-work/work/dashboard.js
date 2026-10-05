/* ===== SCRIPT #2 @287481 attrs= len=794 */

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
    
/* ===== SCRIPT #6 @295949 attrs= len=469 */

        // ✅ V2 SEMPRE USA TEMA DARK (forçado após demo-theme.min.js)
        // Garante que o dark seja aplicado mesmo se o demo-theme.min.js tentar aplicar light
        (function() {
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            document.body.setAttribute('data-bs-theme', 'dark');
        })();
    
/* ===== SCRIPT #7 @325930 attrs= len=232 */

    const btn = document.querySelector('#btnShowMenuV2');
    const menuDropdown = document.querySelector('.dropdownMenuProfileV2');

    btn.addEventListener('click', () => {
        menuDropdown.classList.toggle('upV2');
    });

/* ===== SCRIPT #8 @341794 attrs= len=3598 */

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

/* ===== SCRIPT #9 @451068 attrs= len=2200 */

                                        document.addEventListener("DOMContentLoaded", function() {
                                            window.tomSelects = window.tomSelects || {};
                                            var el = document.getElementById('make-headlines-select-3');
                                            const instance = window.TomSelect && (new TomSelect(el, {
                                                copyClassesToDropdown: false,
                                                dropdownParent: 'body',
                                                controlInput: '<input>',
                                                render: {
                                                    item: function(data, escape) {
                                                        if (data.customProperties) {
                                                            return '<div><span class="dropdown-item-indicator">' + data
                                                                .customProperties + '</span>' + escape(data.text) + '</div>';
                                                        }
                                                        return '<div>' + escape(data.text) + '</div>';
                                                    },
                                                    option: function(data, escape) {
                                                        if (data.customProperties) {
                                                            return '<div><span class="dropdown-item-indicator">' + data
                                                                .customProperties + '</span>' + escape(data.text) + '</div>';
                                                        }
                                                        return '<div>' + escape(data.text) + '</div>';
                                                    },
                                                },
                                            }));
                                            window.tomSelects[el.id] = instance;
                                        });
                                    
/* ===== SCRIPT #10 @455818 attrs= len=2200 */

                                        document.addEventListener("DOMContentLoaded", function() {
                                            window.tomSelects = window.tomSelects || {};
                                            var el = document.getElementById('make-headlines-select-4');
                                            const instance = window.TomSelect && (new TomSelect(el, {
                                                copyClassesToDropdown: false,
                                                dropdownParent: 'body',
                                                controlInput: '<input>',
                                                render: {
                                                    item: function(data, escape) {
                                                        if (data.customProperties) {
                                                            return '<div><span class="dropdown-item-indicator">' + data
                                                                .customProperties + '</span>' + escape(data.text) + '</div>';
                                                        }
                                                        return '<div>' + escape(data.text) + '</div>';
                                                    },
                                                    option: function(data, escape) {
                                                        if (data.customProperties) {
                                                            return '<div><span class="dropdown-item-indicator">' + data
                                                                .customProperties + '</span>' + escape(data.text) + '</div>';
                                                        }
                                                        return '<div>' + escape(data.text) + '</div>';
                                                    },
                                                },
                                            }));
                                            window.tomSelects[el.id] = instance;
                                        });
                                    
/* ===== SCRIPT #11 @478598 attrs= len=19999 */

    document.querySelectorAll('.btn-advanced-options').forEach(btn => {
        btn.addEventListener('click', function() {
            this.classList.toggle('btn-show-advanced-options');
            if (this.classList.contains('btn-show-advanced-options')) {
                this.innerHTML = `
                Esconder Opções Avançadas
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-chevron-up-icon lucide-chevron-up"><path d="m18 15-6-6-6 6"/></svg>
            `;
            } else {
                this.innerHTML = `
                Opções Avançadas
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-chevron-down-icon lucide-chevron-down"><path d="m6 9 6 6 6-6"/></svg>
            `;
            }
        });
    })

    var customRange = document.querySelector('#customRange');

    if (customRange) customRange.addEventListener('change', (e) => {
        const currentElement = e.target;
        const cValue = currentElement.value;
        let activeLabel = "balanced";
        if (cValue < 25) {
            currentElement.value = 0
            activeLabel = "essential";
        } else if (cValue < 75) {
            currentElement.value = 50
        } else {
            currentElement.value = 100
            activeLabel = "explorer";
        }

        document.querySelectorAll('.readlineTone').forEach(readlineTone => {
            readlineTone.classList.remove('active');
        });

        const activeTone = document.getElementById(activeLabel);
        if (activeTone) activeTone.classList.add('active');

        currentElement.style.background =
            `linear-gradient(to right, #9945FF ${currentElement.value}%, #4C1F83 ${currentElement.value}%)`;

    });

    var progressInterval;
    var currentProgress = 0;
    var progressMessages = [{
            text: 'Separando referências...',
            description: 'Organizando dados para criar headlines personalizadas'
        },
        {
            text: 'Aplicando inteligência...',
            description: 'Processando conteúdo com algoritmos avançados'
        },
        {
            text: 'Analisando tendências...',
            description: 'Identificando padrões virais e engajamento'
        },
        {
            text: 'Gerando estruturas...',
            description: 'Criando frameworks de headlines otimizadas'
        },
        {
            text: 'Personalizando conteúdo...',
            description: 'Adaptando para seu perfil e audiência'
        },
        {
            text: 'Finalizando headlines...',
            description: 'Aplicando toques finais de qualidade'
        },
        {
            text: 'Quase pronto...',
            description: 'Preparando resultado final'
        }
    ];

    window.showProgressAnimation = function(headlineId) {
        console.log('showProgressAnimation chamada com ID:', headlineId);

        // Esconder o formulário principal e as opções
        document.querySelector('.thinkForMe').style.display = 'none';
        document.querySelectorAll('.j_content_make_headlines').forEach(el => {
            el.style.display = 'none';
        });

        // Esconder as opções de "Falar sobre" (Assuntos Virais/Escolher Assunto)
        // Esconder todo o container das opções
        const optionsContainer = document.querySelector('.form-selectgroup-boxes');
        if (optionsContainer) {
            optionsContainer.parentElement.style.display = 'none';
        }

        // Esconder o botão de submit para evitar cliques duplos
        const submitButton = document.getElementById('make_headlines_button');
        if (submitButton) {
            submitButton.style.display = 'none';
        }

        const advancedOptionsButton = document.getElementById('set_headlines_categories');
        if (advancedOptionsButton) {
            advancedOptionsButton.style.display = 'none';
        }

        const advancedOptionsButton2 = document.getElementById('set_headlines_categories-2');
        if (advancedOptionsButton2) {
            advancedOptionsButton2.style.display = 'none';
        }

        // Mostrar seção de progresso
        document.getElementById('headline-progress-section').style.display = 'block';

        console.log('Seção de progresso exibida');

        // Iniciar animação de progresso
        startProgressAnimation();

        // Iniciar polling para verificar status
        startStatusPolling(headlineId);
    }

    function startProgressAnimation() {
        let messageIndex = 0;
        let lastMessageChange = Date.now();

        progressInterval = setInterval(() => {
            // Progresso mais lento: 0.5% a cada 1 segundo (100% em ~3 minutos)
            currentProgress += Math.random() * 0.8; // Progresso aleatório entre 0-0.8%

            if (currentProgress > 90) {
                currentProgress = 90; // Não ultrapassar 90% até completar
            }

            // Atualizar barra de progresso
            document.getElementById('progress-bar').style.width = currentProgress + '%';
            document.getElementById('progress-text').textContent = Math.round(currentProgress) + '% concluído';

            // Trocar mensagem a cada 15 segundos (em vez de por progresso)
            const now = Date.now();
            if (now - lastMessageChange > 15000 && messageIndex < progressMessages.length - 1) {
                messageIndex++;
                updateProgressMessage(progressMessages[messageIndex]);
                lastMessageChange = now;
            }

        }, 1000); // Intervalo de 1 segundo em vez de 500ms
    }

    function updateProgressMessage(message) {
        document.getElementById('progress-message').innerHTML = `
        <strong>${message.text}</strong><br>
        <small>${message.description}</small>
    `;
    }

    function startStatusPolling(headlineId) {
        const pollingInterval = setInterval(() => {
            fetch(`/dashboard/user/headlines/status/${headlineId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        if (data.status === 'completed') {
                            clearInterval(pollingInterval);
                            clearInterval(progressInterval);
                            handleCompletion(data, headlineId);
                        } else if (data.status === 'error') {
                            clearInterval(pollingInterval);
                            clearInterval(progressInterval);
                            handleError(data.message);
                        }
                        // Status in_gpt2 significa que está processando
                        console.log('Status atual:', data.status);
                    }
                })
                .catch(error => {
                    console.error('Erro no polling:', error);
                });
        }, 20000); // Verificar a cada 20 segundos
    }

    function handleCompletion(data, headlineId) {
        // Parar a animação de progresso
        clearInterval(progressInterval);

        // Completar barra de progresso
        document.getElementById('progress-bar').style.width = '100%';
        document.getElementById('progress-text').textContent = '100% concluído';
        document.getElementById('progress-bar').classList.remove('progress-bar-animated');
        document.getElementById('progress-bar').classList.add('bg-success');

        updateProgressMessage({
            text: 'Concluído!',
            description: 'Suas headlines estão prontas!'
        });

        // Mostrar sucesso e preparar para fechar
        setTimeout(() => {
            toastr.success('Headlines geradas com sucesso!');

            // Mostrar mensagem de redirecionamento
            updateProgressMessage({
                text: 'Redirecionando...',
                description: 'Você será redirecionado para ver suas headlines'
            });

            // Fechar modal e recarregar página
            setTimeout(() => {
                const modal = bootstrap.Modal.getInstance(document.getElementById(
                    'modal-make-headlines'));
                if (modal) {
                    modal.hide();
                }

                // Recarregar página com parâmetro da headline
                const currentUrl = new URL(window.location);
                currentUrl.searchParams.set('headline', headlineId);
                window.location.href = currentUrl.toString();
            }, 2000);

        }, 1500);
    }

    function handleError(message) {
        // Parar a animação de progresso
        clearInterval(progressInterval);

        updateProgressMessage({
            text: 'Erro no processamento',
            description: message || 'Ocorreu um erro inesperado'
        });

        document.getElementById('progress-bar').classList.remove('progress-bar-animated');
        document.getElementById('progress-bar').classList.add('bg-danger');
        document.getElementById('progress-text').textContent = 'Erro no processamento';

        setTimeout(() => {
            toastr.error('Erro ao processar headlines: ' + (message || 'Erro desconhecido'));

            // Mostrar botão para tentar novamente ou fechar
            updateProgressMessage({
                text: 'Processamento falhou',
                description: 'Clique em fechar para tentar novamente'
            });

            // Fechar modal após delay
            setTimeout(() => {
                const modal = bootstrap.Modal.getInstance(document.getElementById(
                    'modal-make-headlines'));
                if (modal) {
                    modal.hide();
                }
            }, 3000);
        }, 1500);
    }

    document.addEventListener('DOMContentLoaded', function() {
        const hasViralTopics = false;

        // Adicionar listener para mudança de opção
        const radioButtons = document.querySelectorAll('input[name="who"]');
        const divViralTopics = document.querySelectorAll('.divViralTopics');
        const divCustomSubject = document.querySelectorAll('.divCustomSubject');
        const viralTopicsLabel = document.getElementById('viral-topics-label');

        const formViral = document.querySelectorAll('#make-headlines-viral');
        const formHeadlines = document.querySelectorAll('#make-headlines-me');

        const whoChoose = document.querySelector('input[name="who-choose"]');
        if (whoChoose) {
            whoChoose.addEventListener('click', (event) => {
                // Alterna visibilidade ao clicar
                if (event.target.dataset.active === "true") {
                    event.target.checked = false; // desmarca
                    event.target.dataset.active = "false";

                    divCustomSubject.forEach(el => { el.style.display = 'none'; });
                    if (hasViralTopics) {
                        divViralTopics.forEach(el => { el.style.display = 'block'; });
                    }
                } else {
                    event.target.dataset.active = "true";
                    formViral.forEach(el => { el.style.display = 'block'; });
                    divViralTopics.forEach(el => { el.style.display = 'none'; });
                    divCustomSubject.forEach(el => { el.style.display = 'block'; });
                }
            });
        }

        function handleWhoChange(selectedValue) {
            formViral.forEach(el => { el.style.display = 'none'; });
            formHeadlines.forEach(el => { el.style.display = 'none'; });

            if (selectedValue === 'viral') {
                formViral.forEach(el => { el.style.display = 'block'; });
                // Se não há assuntos virais, mostrar apenas campo customizado
                if (!hasViralTopics) {
                    divViralTopics.forEach(el => { el.style.display = 'none'; });
                    divCustomSubject.forEach(el => { el.style.display = 'block'; });
                } else {
                    // Se há assuntos virais, mostrar select normalmente
                    divViralTopics.forEach(el => { el.style.display = 'block'; });
                    divCustomSubject.forEach(el => { el.style.display = 'none'; });
                }
            } else if (selectedValue === 'public' || selectedValue === 'me') {
                formHeadlines.forEach(el => { el.style.display = 'block'; });
            }
        }

        radioButtons.forEach(radio => {
            radio.addEventListener('change', function() {
                handleWhoChange(this.value);
            });
        });

        // Selecionar opção inicial (respeita ?who=public|me|viral da URL)
        const whoFromUrl = new URLSearchParams(window.location.search).get('who');
        if (whoFromUrl && ['public', 'me', 'viral'].includes(whoFromUrl)) {
            const radioMatch = document.querySelector(`input[name="who"][value="${whoFromUrl}"]`);
            if (radioMatch) {
                radioMatch.checked = true;
                radioMatch.dispatchEvent(new Event('change'));
            }
        } else if (!hasViralTopics) {
            const publicRadio = document.querySelector('input[name="who"][value="public"]');
            if (publicRadio) {
                publicRadio.checked = true;
                publicRadio.dispatchEvent(new Event('change'));
            }
        } else {
            const viralRadio = document.querySelector('input[name="who"][value="viral"]');
            if (viralRadio) {
                viralRadio.checked = true;
                viralRadio.dispatchEvent(new Event('change'));
            }
        }

        const initialCheckedRadio = document.querySelector('input[name="who"]:checked');
        if (initialCheckedRadio) {
            handleWhoChange(initialCheckedRadio.value);
        }

        // Controle de seleção exclusiva entre Perfil de Referência e Formato do Vídeo
        const referenceTypeRadios = document.querySelectorAll('.reference-type-radio');
        const profileSection = document.getElementById('profile-reference-section');
        const formatSection = document.getElementById('format-video-section');
        const profileSelect = document.getElementById('make-headlines-profiles');
        const formatSelect = document.getElementById('make-headlines-format-videos');

        // Função para carregar perfis via AJAX
        function loadProfiles() {
            const profileSelect = document.getElementById('make-headlines-profiles');
            
            // Verificar se já foram carregados
            if (profileSelect && profileSelect.dataset.loaded === 'true') {
                return;
            }

            fetch('https://corestudio.ai/dashboard/user/headlines/profiles')
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.profiles && profileSelect) {
                        // Limpar opções existentes
                        profileSelect.innerHTML = '<option value="">Selecione os perfis de referência</option>';
                        
                        // Adicionar perfis
                        data.profiles.forEach(profile => {
                            const option = document.createElement('option');
                            option.value = profile.id;
                            option.textContent = profile.profile + (profile.is_structure == 0 ? ' (Sem estruturas disponíveis)' : '');
                            if (profile.is_structure == 0) {
                                option.disabled = true;
                            }
                            profileSelect.appendChild(option);
                        });

                        // Marcar como carregado
                        profileSelect.dataset.loaded = 'true';
                    }
                })
                .catch(error => {
                    console.error('Erro ao carregar perfis:', error);
                    if (profileSelect) {
                        profileSelect.innerHTML = '<option value="">Erro ao carregar perfis</option>';
                    }
                });
        }

        // Função para limpar seleções do TomSelect
        function clearTomSelectSelection(selectElement) {
            if (selectElement && selectElement.tomselect) {
                selectElement.tomselect.clear();
            } else if (selectElement) {
                // Se TomSelect não estiver inicializado ainda, limpar select normal
                selectElement.value = '';
                const options = selectElement.querySelectorAll('option');
                options.forEach(option => option.selected = false);
            }
        }

        // Função para gerenciar a exibição das seções
        function handleReferenceTypeChange(selectedValue) {
            if (selectedValue === 'profile') {
                // Mostrar seção de perfil e esconder formato
                profileSection.style.display = 'block';
                formatSection.style.display = 'none';

                // Limpar seleção de formato
                clearTomSelectSelection(formatSelect);

                // Ajustar largura para ocupar toda a linha
                profileSection.classList.remove('col-md-6');
                profileSection.classList.add('col-md-12');

            } else if (selectedValue === 'format') {
                // Mostrar seção de formato e esconder perfil
                formatSection.style.display = 'block';
                profileSection.style.display = 'none';

                // Limpar seleção de perfil
                clearTomSelectSelection(profileSelect);

                // Ajustar largura para ocupar toda a linha
                formatSection.classList.remove('col-md-6');
                formatSection.classList.add('col-md-12');
            }
        }

        // Adicionar listeners aos radio buttons
        referenceTypeRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.checked) {
                    handleReferenceTypeChange(this.value);
                }
            });
        });

        // Limpar seleções quando o modal for fechado ou campos forem limpos
        const clearFieldsButton = document.querySelectorAll('.j_make_headlines_clear_fields');
        clearFieldsButton.forEach(button => {
            button.addEventListener('click', function() {
                // Desmarcar radio buttons de tipo de referência
                referenceTypeRadios.forEach(radio => radio.checked = false);

                // Esconder ambas as seções
                profileSection.style.display = 'none';
                formatSection.style.display = 'none';

                // Limpar seleções
                clearTomSelectSelection(profileSelect);
                clearTomSelectSelection(formatSelect);
            });
        });

        // Quando o modal for aberto, carregar perfis
        const modal = document.getElementById('modal-make-headlines');
        if (modal) {
            modal.addEventListener('shown.bs.modal', function() {
                loadProfiles();
            });

            modal.addEventListener('hidden.bs.modal', function() {
                // Desmarcar radio buttons
                referenceTypeRadios.forEach(radio => radio.checked = false);

                // Esconder seções
                profileSection.style.display = 'none';
                formatSection.style.display = 'none';

                // Limpar seleções
                clearTomSelectSelection(profileSelect);
                clearTomSelectSelection(formatSelect);
            });
        }
    });

/* ===== SCRIPT #12 @651673 attrs= len=2991 */

        const customRange = document.querySelector('#customRange');
        customRange.addEventListener('change', (e) => {
            const currentElement = e.target;
            const cValue = currentElement.value;
            let activeLabel = "balanced";
            if (cValue < 25) {
                currentElement.value = 0
                activeLabel = "essential";
            } else if (cValue < 75) {
                currentElement.value = 50
            } else {
                currentElement.value = 100
                activeLabel = "explorer";
            }

            document.querySelectorAll('.readlineTone').forEach(readlineTone => {
                readlineTone.classList.remove('active');
            });

            document.getElementById(activeLabel).classList.add('active');

            currentElement.style.background =
                `linear-gradient(to right, #9945FF ${currentElement.value}%, #4C1F83 ${currentElement.value}%)`;

        });

        const headlineTypes = document.querySelectorAll('.radioGenerationType');
        headlineTypes.forEach(headlineType => {
            headlineType.addEventListener('click', () => {
                if (headlineType.querySelector('input').disabled) return;

                headlineTypes.forEach(headlineType => {
                    headlineType.classList.remove('active');
                });

                headlineType.classList.add('active');
            });
        });


        document.querySelector('#openAdvancedOptionsModal').addEventListener('click', function() {
            this.innerHTML = this.innerText === 'Opções Avançadas' ?
                `
                Esconder Opções Avançadas
                <svg style="width: 18px; margin-left: 5px" xmlns="http://www.w3.org/2000/svg" width="24" height="24"
                    viewBox="0 0 24 24" fill="none"  stroke="currentColor" stroke-width="2" stroke-linecap="round"
                    stroke-linejoin="round" class="lucide lucide-chevron-up-icon lucide-chevron-up">
                    <path d="m18 15-6-6-6 6"/>
                </svg>
            ` :
                `
                Opções Avançadas
                 <svg style="width: 18px; margin-left: 5px" xmlns="http://www.w3.org/2000/svg" width="24"
                    height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                    class="lucide lucide-chevron-down-icon lucide-chevron-down">
                    <path d="m6 9 6 6 6-6" />
                </svg>
            `;
            document.getElementById('advancedOptionsV2ID').classList.toggle('show');
        })

        document.querySelector('#clearFieldsV2').addEventListener('click', function() {
            selects.forEach(element => {
                document.getElementById(element).value = [];
                document.getElementById(element).tomselect.clear();
            });
        });
    
/* ===== SCRIPT #13 @654744 attrs= len=2313 */

        // Função para editar headline
        function editHeadline(headlineId) {
            // Buscar a headline no DOM
            const headlineRow = document.querySelector(`.avatar[data-headline-id="${headlineId}"]`).closest(
                '.headline-item');
            const headlineText = headlineRow.querySelector('.text-primary').textContent.trim();

            // Preencher o modal
            document.getElementById('editHeadlineInput').value = headlineText;
            document.getElementById('editHeadlineId').value = headlineId;

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('editHeadlineModal'));
            modal.show();
        }

        // Função para abrir link do vídeo
        function openVideoLink(link) {
            if (link && link !== '#') {
                window.open(link, '_blank');
            } else {
                alert('Link do vídeo não disponível');
            }
        }

        // Função para criar roteiro
        function createRoadmap(headlineId) {
            console.log('Criar roteiro para headline:', headlineId);
            document.getElementById('roadmapContent').value = '';

            // Buscar a headline no DOM
            const headlineRow = document.querySelector(`.avatar[data-headline-id="${headlineId}"]`).closest(
                '.headline-item');
            const headlineText = headlineRow.querySelector('.text-primary').textContent.trim();

            // Preencher o modal
            document.getElementById('roadmapHeadline').value = headlineText;
            document.getElementById('roadmapHeadlineId').value = headlineId;

            // Mostrar estado inicial (formulário)
            showRoadmapState('form');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
            modal.show();
        }

        // Função para ordenar por views (exemplo)
        function sortByViews() {
            // TODO: Implementar ordenação por views
            console.log('Ordenando por views...');
        }

        // Função para ordenar por data (exemplo)
        function sortByDate() {
            // TODO: Implementar ordenação por data
            console.log('Ordenando por data...');
        }
    
/* ===== SCRIPT #21 @669583 attrs= len=1020 */

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

/* ===== SCRIPT #23 @670716 attrs= len=1352 */

    // Configuração das rotas para o componente
    window.AdvancedRoadmapModalConfig = {
        routes: {
            generateQuestions: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/generate-questions",
            store: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/store",
            show: "https://corestudio.ai/dashboard/user/roadmaps/check-status/__ID__",
            chat: "https://corestudio.ai/dashboard/user/chat/__ID__",
            updateRoadmap: "https://corestudio.ai/dashboard/user/roadmaps/update",
            updateSuggested: "https://corestudio.ai/dashboard/user/headlines/suggested/update",
            updateFavorites: "https://corestudio.ai/dashboard/user/headlines/favorites/update",
            listSearch: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/list-search",
            directSearch: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/direct-search",
            translateSearchQuery: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-query",
            translateSearchResults: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-results"
        },
        csrfToken: "HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC"
    };


/* ===== SCRIPT #34 @673041 attrs= len=268 */

        $(document).ready(function() {
            $("#filterSelectV2").on("change", function() {
                var value = $(this).val();
                window.location.href = "https://corestudio.ai/dashboard/user?filter=" + value;
            })
        });
    
/* ===== SCRIPT #35 @673333 attrs= len=19150 */

        // Função para abrir modal de roteiro avançado com headline customizada
        function openAdvancedRoadmapWithCustomHeadline() {
            // Verificar se o AdvancedRoadmapModal está disponível
            if (typeof AdvancedRoadmapModal === 'undefined') {
                console.error('AdvancedRoadmapModal não está definido. Recarregando a página...');
                toastr.warning('Atualizando a página para carregar os recursos necessários...');
                // Forçar reload sem cache
                setTimeout(function() {
                    window.location.reload(true);
                }, 1000);
                return;
            }
            // Abrir modal sem ID, permitindo que o usuário digite a headline
            AdvancedRoadmapModal.openWithCustomHeadline('');
        }

        $(document).ready(function() {
            $('#ai-search-input').keypress(function(e) {
                if (e.which == 13) {
                    e.preventDefault();

                    var query = $(this).val().trim();
                    if (!query) return;

                    // Adiciona mensagem do usuário
                    addMessage('user', query);

                    // Desabilita o input e mostra loading
                    $(this).prop('disabled', true);
                    $(this).attr('placeholder', 'Processando...');

                    $.ajax({
                        url: 'https://corestudio.ai/dashboard/user/mamanai/proccess',
                        type: 'POST',
                        data: {
                            _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                            query: query
                        },
                        success: function(data) {
                            if (data.success) {
                                // Adiciona resposta do assistente
                                addMessage('assistant', data.response);
                            } else {
                                toastr.error(data.message ||
                                    'Erro ao processar sua solicitação');
                            }
                        },
                        error: function(xhr) {
                            toastr.error('Erro ao processar sua solicitação');
                            console.error(xhr);
                        },
                        complete: function() {
                            // Reabilita o input
                            $('#ai-search-input').prop('disabled', false);
                            $('#ai-search-input').attr('placeholder',
                                'O que vamos criar hoje?');
                            $('#ai-search-input').val('');
                        }
                    });
                }
            });

            function addMessage(type, content) {
                const time = new Date().toLocaleTimeString();
                const messageHtml = `
            <div class="chat-message ${type}-message">
                <div class="message-content">${content}</div>
                <div class="message-time">${time}</div>
            </div>
        `;

                $('#chat-messages').append(messageHtml);

                // Scroll para a última mensagem
                const chatMessages = document.getElementById('chat-messages');
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        });

        // Inicializar dropdowns do Bootstrap
        document.addEventListener('DOMContentLoaded', function() {
            // Inicializar todos os dropdowns do Bootstrap
            var dropdownElementList = [].slice.call(document.querySelectorAll('.dropdown-toggle'));
            var dropdownList = dropdownElementList.map(function(dropdownToggleEl) {
                return new bootstrap.Dropdown(dropdownToggleEl);
            });

            // Event delegation APENAS para os dropdowns do index (que têm data-action)
            document.addEventListener('click', function(e) {
                // Verificar se o elemento clicado tem data-action E está dentro de um dropdown do index
                if (e.target.classList.contains('dropdown-item') && e.target.hasAttribute('data-action')) {
                    e.preventDefault();

                    var action = e.target.getAttribute('data-action');
                    var headlineId = e.target.getAttribute('data-headline-id');
                    var link = e.target.getAttribute('data-link');

                    // Processar apenas ações específicas do index
                    switch (action) {
                        case 'create-roadmap':
                            createRoadmap(headlineId);
                            break;
                        case 'edit-headline':
                            editHeadline(headlineId);
                            break;
                        case 'open-link':
                            openPostLink(link);
                            break;
                        case 'view-roadmap':
                            viewRoadmap(headlineId);
                            break;
                    }
                }
            });
        });

        function createRoadmap(headlineId) {
            console.log('Criar roteiro para headline:', headlineId);
            document.getElementById('roadmapContent').value = '';

            // Buscar a headline no DOM
            const headlineRow = document.querySelector(`.avatar[data-headline-id="${headlineId}"]`).closest(
                '.headline-item');
            console.log(document.querySelector('.avatar'));
            const headlineText = headlineRow.querySelector('.text-primary').textContent.trim();

            // Preencher o modal
            document.getElementById('roadmapHeadline').value = headlineText;
            document.getElementById('roadmapHeadlineId').value = headlineId;

            // Mostrar estado inicial (formulário)
            showRoadmapState('form');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
            modal.show();
        }

        function editHeadline(headlineId) {
            // Buscar a headline no DOM
            const headlineRow = document.querySelector(`.avatar[data-headline-id="${headlineId}"]`).closest(
                '.headline-item');
            const headlineText = headlineRow.querySelector('.text-primary').textContent.trim();

            // Preencher o modal
            document.getElementById('editHeadlineInput').value = headlineText;
            document.getElementById('editHeadlineId').value = headlineId;

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('editHeadlineModal'));
            modal.show();
        }

        function showRoadmapState(state) {
            // Esconder todos os estados
            document.getElementById('creatingRoadmapState').style.display = 'none';
            document.getElementById('createRoadmapFormState').style.display = 'none';
            document.getElementById('roadmapCreatedState').style.display = 'none';

            // Mostrar o estado solicitado
            switch (state) {
                case 'creating':
                    document.getElementById('creatingRoadmapState').style.display = 'block';
                    document.getElementById('createRoadmapBtn').style.display = 'none';
                    break;
                case 'form':
                    document.getElementById('createRoadmapFormState').style.display = 'block';
                    document.getElementById('createRoadmapBtn').style.display = 'inline-block';
                    break;
                case 'result':
                    document.getElementById('roadmapCreatedState').style.display = 'block';
                    document.getElementById('createRoadmapBtn').style.display = 'none';
                    break;
            }
        }

        function saveRoadmap() {
            const headlineId = document.getElementById('roadmapHeadlineId').value;
            const roadmapContent = document.getElementById('roadmapContent').value.trim();

            if (!roadmapContent) {
                toastr.error('Por favor, preencha as observações adicionais');
                return;
            }

            // Mostrar estado de criação
            showRoadmapState('creating');

            // AJAX para criar roteiro no backend
            $.ajax({
                url: "dashboard/user/roadmaps/reversa/store",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    headline_id: headlineId,
                    observations: roadmapContent
                },
                success: function(data) {
                    if (data.success) {
                        // Preencher o resultado
                        document.getElementById('roadmapHeadlineResult').value = document.getElementById(
                            'roadmapHeadline').value;
                        document.getElementById('roadmapResult').value = data.roadmap_engreversa.text ||
                            'Roteiro criado com sucesso!';

                        // Mostrar estado de resultado
                        showRoadmapState('result');

                        toastr.success('Roteiro criado com sucesso!');
                    } else {
                        // Voltar para o formulário em caso de erro
                        showRoadmapState('form');
                        toastr.error(data.message || 'Erro ao criar o roteiro');
                    }
                },
                error: function(xhr) {
                    // Voltar para o formulário em caso de erro
                    showRoadmapState('form');
                    toastr.error('Erro ao criar o roteiro');
                    console.error(xhr);
                }
            });
        }

        function copyRoadmap() {
            const roadmapText = document.getElementById('roadmapResult').value;

            if (navigator.clipboard) {
                navigator.clipboard.writeText(roadmapText).then(function() {
                    toastr.success('Roteiro copiado para a área de transferência!');
                }).catch(function() {
                    fallbackCopyTextToClipboard(roadmapText);
                });
            } else {
                fallbackCopyTextToClipboard(roadmapText);
            }
        }

        function fallbackCopyTextToClipboard(text) {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                document.execCommand('copy');
                toastr.success('Roteiro copiado para a área de transferência!');
            } catch (err) {
                toastr.error('Erro ao copiar o roteiro');
                console.error('Fallback: Oops, unable to copy', err);
            }

            document.body.removeChild(textArea);
        }

        function editRoadmap() {
            const roadmapText = document.getElementById('roadmapResult').value;
            document.getElementById('roadmapContent').value = roadmapText;

            // Voltar para o formulário para edição
            showRoadmapState('form');

            // Focar no campo de observações
            document.getElementById('roadmapContent').focus();
        }

        function saveHeadline() {
            const headlineId = document.getElementById('editHeadlineId').value;
            const newHeadline = document.getElementById('editHeadlineInput').value.trim();

            if (!newHeadline) {
                toastr.error('Por favor, preencha a headline');
                return;
            }

            // AJAX para salvar no backend
            $.ajax({
                url: "dashboard/user/headlines/reversa/update",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    headline: newHeadline,
                    id: headlineId
                },
                success: function(data) {
                    if (data.success) {
                        // Atualizar no DOM
                        const headlineRow = document.querySelector(`.avatar[data-headline-id="${headlineId}"]`)
                            .closest('.headline-item');
                        headlineRow.querySelector('.text-primary').textContent = newHeadline;

                        // Fechar modal
                        const modal = bootstrap.Modal.getInstance(document.getElementById('editHeadlineModal'));
                        modal.hide();

                        toastr.success('Headline atualizada com sucesso!');
                    } else {
                        toastr.error(data.message || 'Erro ao atualizar a headline');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao atualizar a headline');
                    console.error(xhr);
                }
            });
        }

        function viewRoadmap(headlineId) {
            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('viewHeadlineFlowModal'));
            modal.show();
        }

        function copyViewRoadmap() {
            const roadmapText = document.getElementById('viewRoadmapContent').value;

            if (navigator.clipboard) {
                navigator.clipboard.writeText(roadmapText).then(function() {
                    toastr.success('Roteiro copiado para a área de transferência!');
                }).catch(function() {
                    fallbackCopyTextToClipboard(roadmapText);
                });
            } else {
                fallbackCopyTextToClipboard(roadmapText);
            }
        }


        function editViewRoadmap() {
            const headlineText = document.getElementById('viewRoadmapHeadline').value;
            const roadmapText = document.getElementById('viewRoadmapContent').value;

            // Preencher o modal de criação com o conteúdo para edição
            document.getElementById('roadmapHeadline').value = headlineText;
            document.getElementById('roadmapContent').value = roadmapText;

            // Abrir o modal de criação
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
            modal.show();
        }

        // Função para abrir link do vídeo
        function openVideoLink(link) {
            if (link && link !== '#') {
                window.open(link, '_blank');
            } else {
                alert('Link do vídeo não disponível');
            }
        }

        // Função para abrir link do post
        function openPostLink(link) {
            console.log('Tentando abrir link:', link);
            if (link && link !== '#' && link !== '') {
                try {
                    window.open(link, '_blank');
                } catch (e) {
                    console.error('Erro ao abrir link:', e);
                    // Fallback: tentar abrir em nova aba
                    const linkElement = document.createElement('a');
                    linkElement.href = link;
                    linkElement.target = '_blank';
                    linkElement.rel = 'noopener noreferrer';
                    document.body.appendChild(linkElement);
                    linkElement.click();
                    document.body.removeChild(linkElement);
                }
            } else {
                console.log('Link inválido:', link);
                toastr.warning('Link não disponível para esta headline');
            }
        }

        $(".view-flow-headline").click(function() {
            const headlineId = $(this).data('headline-id');
            $.ajax({
                url: "dashboard/user/headlines/suggested/view/" + headlineId,
                type: 'GET',
                success: function(data) {
                    if (data.success) {
                        data = data.data;

                        // Função para extrair conteúdo do JSON
                        function extractContent(jsonString) {
                            if (!jsonString) return 'Nenhum dado encontrado';

                            try {
                                let parsed;

                                // Se já é um objeto, usa diretamente
                                if (typeof jsonString === 'object') {
                                    parsed = jsonString;
                                } else {
                                    // Se é string, tenta fazer parse
                                    parsed = JSON.parse(jsonString);
                                }

                                // Se é um array, pega o primeiro item
                                if (Array.isArray(parsed) && parsed.length > 0) {
                                    parsed = parsed[0];
                                }

                                // Extrai o campo 'content' se existir
                                if (parsed && parsed.content) {
                                    return parsed.content;
                                }

                                // Se não tem content, retorna o JSON formatado
                                return JSON.stringify(parsed, null, 2);
                            } catch (e) {
                                // Se não conseguir fazer parse, retorna o texto original
                                return jsonString;
                            }
                        }

                        // Preencher os campos extraindo o conteúdo
                        document.getElementById('headline_payload_old_1').value = extractContent(data
                            .payload_headline_old_1);
                        document.getElementById('headline_callback_old_1').value = extractContent(data
                            .callback_headline_old_1);
                        document.getElementById('headline_payload').value = extractContent(data
                            .payload_headline);
                        document.getElementById('headline_callback').value = extractContent(data
                            .headline);

                        const modal = new bootstrap.Modal(document.getElementById(
                            'viewHeadlineFlowModal'));
                        modal.show();
                    } else {
                        toastr.error(data.message || 'Erro ao buscar o roteiro');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao buscar o roteiro');
                    console.error(xhr);
                }
            });
        });
    
/* ===== SCRIPT #36 @692506 attrs= len=6342 */

        // Função para ajustar altura
        function adjustTextareaHeight(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = (textarea.scrollHeight) + 'px';
        }

        // Função para ajustar todos os textareas
        function adjustAllTextareas() {
            document.querySelectorAll('.auto-resize').forEach(function(textarea) {
                adjustTextareaHeight(textarea);
            });
        }

        // Ajusta imediatamente após o DOM carregar
        document.addEventListener('DOMContentLoaded', function() {
            // Ajusta inicialmente
            adjustAllTextareas();
            //$(".thinkForMe").css("display", "none");

            // Ajusta após um pequeno delay para garantir que todo conteúdo foi carregado
            setTimeout(adjustAllTextareas, 100);

            // Adiciona listeners para eventos
            document.querySelectorAll('.auto-resize').forEach(function(textarea) {
                textarea.addEventListener('input', function() {
                    adjustTextareaHeight(this);
                });

                textarea.addEventListener('focus', function() {
                    adjustTextareaHeight(this);
                });
            });
        });

        // Ajusta quando a janela é redimensionada
        window.addEventListener('resize', adjustAllTextareas);

        // Ajusta quando o conteúdo é modificado dinamicamente
        const observer = new MutationObserver(function(mutations) {
            adjustAllTextareas();
        });

        // Observa mudanças no documento
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true
        });

        // Inicializar TomSelects para as opções avançadas
        function initializeAdvancedTomSelects() {
            if (window.TomSelect) {
                if(!window.tomSelects) {
                    window.tomSelects = window.tomSelects || {};
                }
                // TomSelect para nichos
                if (!window.tomSelects || !window.tomSelects['make-headlines-niches']) {
                    const nichesEl = document.getElementById('make-headlines-niches');
                    if (nichesEl && !nichesEl.tomselect) {
                        window.tomSelects = window.tomSelects || {};
                        window.tomSelects['make-headlines-niches'] = new TomSelect(nichesEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

                // TomSelect para profissões
                if (!window.tomSelects || !window.tomSelects['make-headlines-professions']) {
                    const professionsEl = document.getElementById('make-headlines-professions');
                    if (professionsEl && !professionsEl.tomselect) {
                        window.tomSelects['make-headlines-professions'] = new TomSelect(professionsEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

                // TomSelect para formatos de vídeo
                if (!window.tomSelects || !window.tomSelects['make-headlines-format-videos']) {
                    const formatVideosEl = document.getElementById('make-headlines-format-videos');
                    if (formatVideosEl && !formatVideosEl.tomselect) {
                        window.tomSelects['make-headlines-format-videos'] = new TomSelect(formatVideosEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

                // TomSelect para gatilhos de atenção
                if (!window.tomSelects || !window.tomSelects['make-headlines-attention-triggers']) {
                    const attentionTriggersEl = document.getElementById('make-headlines-attention-triggers');
                    if (attentionTriggersEl && !attentionTriggersEl.tomselect) {
                        window.tomSelects['make-headlines-attention-triggers'] = new TomSelect(attentionTriggersEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

            }
        }

        // Inicializar TomSelects quando o modal for aberto
        document.addEventListener('DOMContentLoaded', function() {
            // Inicializar imediatamente
            initializeAdvancedTomSelects();

            // Inicializar quando as opções avançadas forem mostradas
            document.addEventListener('click', function(e) {
                if (e.target && e.target.id === 'set_headlines_categories') {
                    setTimeout(function() {
                        initializeAdvancedTomSelects();
                    }, 300); // Aguardar a animação do toggle
                }
            });
        });
    
/* ===== SCRIPT #37 @698870 attrs= len=2677 */

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
    
/* ===== SCRIPT #39 @701640 attrs= len=605 */

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


/* ===== SCRIPT #40 @702264 attrs= len=9045 */

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


/* ===== SCRIPT #41 @711336 attrs= len=1554 */

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
        
/* ===== SCRIPT #42 @716746 attrs= len=1479 */

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
    
/* ===== SCRIPT #43 @718248 attrs=data-navigate-once="true" len=137 */
window.livewireScriptConfig = {"csrf":"HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC","uri":"\/livewire\/update","progressBar":"","nonce":""};
/* ===== SCRIPT #47 @718671 attrs= len=4402 */

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
        
/* ===== SCRIPT #50 @723314 attrs=type="text/javascript" len=361 */

        window.$crisp = [];
        window.CRISP_WEBSITE_ID = "75cc752d-b49d-4b10-9a51-aeb70cf165c3";
                (function() {
            d = document;
            s = d.createElement("script");
            s.src = "https://client.crisp.chat/l.js";
            s.async = 1;
            d.getElementsByTagName("head")[0].appendChild(s);
        })();
    