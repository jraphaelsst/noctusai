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

