/* ===== SCRIPT #29 @344728 attrs= len=17546 */

        // Funções para o modal de roteiro novo
        function createRoadmapNew(headlineId) {
            console.log('Criar roteiro para headline:', headlineId);
            document.getElementById('roadmapContentNew').value = '';

            // Buscar a headline no DOM - usando o botão que foi clicado (ID do elemento)
            const clickedButton = document.getElementById(headlineId);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher o modal
            document.getElementById('roadmapHeadlineNew').value = decodeURIComponent(headlineText);
            document.getElementById('roadmapHeadlineIdNew').value = headlineId;

            // Mostrar estado inicial (formulário)
            showRoadmapStateNew('form');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModalNew'));
            modal.show();
        }

        function showRoadmapStateNew(state) {
            // Esconder todos os estados
            document.getElementById('creatingRoadmapStateNew').style.display = 'none';
            document.getElementById('createRoadmapFormStateNew').style.display = 'none';
            document.getElementById('roadmapCreatedStateNew').style.display = 'none';

            // Mostrar o estado solicitado
            switch (state) {
                case 'creating':
                    document.getElementById('creatingRoadmapStateNew').style.display = 'block';
                    document.getElementById('createRoadmapBtnNew').style.display = 'none';
                    break;
                case 'form':
                    document.getElementById('createRoadmapFormStateNew').style.display = 'block';
                    document.getElementById('createRoadmapBtnNew').style.display = 'inline-block';
                    break;
                case 'result':
                    document.getElementById('roadmapCreatedStateNew').style.display = 'block';
                    document.getElementById('createRoadmapBtnNew').style.display = 'none';
                    break;
            }
        }

        function saveRoadmapNew() {
            const headlineId = document.getElementById('roadmapHeadlineIdNew').value;
            const roadmapContent = document.getElementById('roadmapContentNew').value.trim();

            if (!roadmapContent) {
                toastr.error('Por favor, preencha as observações adicionais');
                return;
            }

            // Mostrar estado de criação
            showRoadmapStateNew('creating');

            // AJAX para criar roteiro no backend
            $.ajax({
                url: "dashboard/user/roadmaps/favorites/store",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    headline_id: headlineId,
                    observations: roadmapContent
                },
                success: function(data) {
                    if (data.success) {
                        // Iniciar long polling para verificar status
                        startLongPollingNew(headlineId);
                    } else {
                        // Voltar para o formulário em caso de erro
                        showRoadmapStateNew('form');
                        toastr.error(data.message || 'Erro ao criar o roteiro');
                    }
                },
                error: function(xhr) {
                    // Voltar para o formulário em caso de erro
                    showRoadmapStateNew('form');
                    toastr.error('Erro ao criar o roteiro');
                    console.error(xhr);
                }
            });
        }

        // Variável global para controlar o polling
        let pollingTimeout = null;
        let isPollingActive = false;

        function startLongPollingNew(headlineId) {
            let pollCount = 0;
            const maxPolls = 60; // Máximo 5 minutos (60 * 5 segundos)
            isPollingActive = true;

            function pollStatus() {
                // Verificar se o polling ainda está ativo
                if (!isPollingActive) {
                    return;
                }
                pollCount += randomNumber(1, 8);

                function randomNumber(min, max) {
                    return Math.floor(Math.random() * (max - min + 1)) + min;
                }

                // Atualizar progresso visual
                updateProgressNew(pollCount, maxPolls);

                $.ajax({
                    url: "dashboard/user/roadmaps/favorites/show-favorites",
                    type: 'POST',
                    data: {
                        _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                        id: headlineId
                    },
                    success: function(data) {
                        if (data.success && data.roadmap_engreversa && data.roadmap_engreversa !==
                            'Roteiro não disponível') {
                            // Roteiro está pronto!
                            document.getElementById('roadmapHeadlineResultNew').value = document.getElementById(
                                'roadmapHeadlineNew').value;
                            document.getElementById('roadmapResultNew').value = data.roadmap_engreversa;

                            // Mostrar estado de resultado
                            showRoadmapStateNew('result');

                            toastr.success('Roteiro criado com sucesso!');
                        } else if (pollCount >= maxPolls) {
                            // Timeout - parar polling
                            showRoadmapStateNew('form');
                            toastr.error(
                                'Timeout: O roteiro está demorando mais que o esperado. Tente novamente.');
                        } else {
                            // Continuar polling em 5 segundos
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    },
                    error: function(xhr) {
                        if (pollCount >= maxPolls) {
                            isPollingActive = false;
                            showRoadmapStateNew('form');
                            toastr.error('Erro ao verificar status do roteiro');
                        } else {
                            // Continuar polling mesmo com erro
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    }
                });
            }

            // Iniciar polling após 2 segundos
            pollingTimeout = setTimeout(pollStatus, 2000);
        }

        function stopPollingNew() {
            isPollingActive = false;
            if (pollingTimeout) {
                clearTimeout(pollingTimeout);
                pollingTimeout = null;
            }
        }

        function cancelRoadmapCreation() {
            // Parar polling
            stopPollingNew();

            // Voltar para o formulário
            showRoadmapStateNew('form');

            // Mostrar mensagem
            toastr.info('Criação de roteiro cancelada');
        }

        function updateProgressNew(current, max) {
            const progress = Math.min((current / max) * 100, 95); // Máximo 95% até estar pronto

            // Atualizar texto de progresso
            const progressText = document.querySelector('#creatingRoadmapStateNew h6');
            if (progressText) {
                progressText.textContent = `Criando seu roteiro... (${Math.round(progress)}%)`;
            }

            // Atualizar barra de progresso
            const progressBar = document.querySelector('#creatingRoadmapStateNew .progress-bar');
            if (progressBar) {
                progressBar.style.width = progress + '%';
                progressBar.setAttribute('aria-valuenow', progress);
            }

            // Atualizar status detalhado
            const statusElement = document.getElementById('progressStatus');
            if (statusElement) {
                let statusText = '';
                if (progress < 20) {
                    statusText = 'Enviando dados para processamento...';
                } else if (progress < 40) {
                    statusText = 'Analisando engenharia reversa...';
                } else if (progress < 60) {
                    statusText = 'Gerando roteiro personalizado...';
                } else if (progress < 80) {
                    statusText = 'Revisando e formatando conteúdo...';
                } else {
                    statusText = 'Finalizando roteiro...';
                }
                statusElement.textContent = statusText;
            }
        }

        function copyRoadmapNew() {
            const roadmapText = document.getElementById('roadmapResultNew').value;

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

        function viewRoadmapNew(headlineId) {
            // Buscar a headline no DOM - usando o ID do elemento
            const clickedButton = document.getElementById(headlineId);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher a headline no modal
            document.getElementById('viewRoadmapHeadlineNew').value = decodeURIComponent(headlineText);

            // Buscar o roteiro via AJAX
            $.ajax({
                url: "dashboard/user/roadmaps/favorites/show-favorites",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    id: headlineId
                },
                success: function(data) {
                    if (data.success) {
                        // Preencher o roteiro no modal
                        document.getElementById('viewRoadmapContentNew').value = data.roadmap_engreversa ||
                            'Roteiro não encontrado';

                        // Verificar se há search_text para mostrar a aba de fontes
                        if (data.search_text && data.search_text.trim() !== '') {
                            console.log('Dados de pesquisa encontrados no roteiro - viewRoadmapNew');
                            // Mostrar a aba de fontes
                            document.getElementById('view-sources-tab-li').style.display = 'block';

                            // Formatar e exibir o search_text
                            let searchTextFormatted = data.search_text.replace(/\n/g, '<br>');
                            document.getElementById('view-search-sources-content').innerHTML =
                                searchTextFormatted;
                        } else {
                            // Esconder a aba de fontes se não houver dados
                            document.getElementById('view-sources-tab-li').style.display = 'none';
                            document.getElementById('view-search-sources-content').innerHTML = '';
                        }

                        // Abrir o modal
                        const modal = new bootstrap.Modal(document.getElementById('viewRoadmapModalNew'));
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
        }

        function copyViewRoadmapNew() {
            const roadmapText = document.getElementById('viewRoadmapContentNew').value;

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

        // Event listener para parar polling quando modal for fechado
        document.addEventListener('hidden.bs.modal', function(e) {
            if (e.target.id === 'createRoadmapModalNew') {
                stopPollingNew();
            }
        });

        // Event delegation para os botões de ação novos
        document.addEventListener('click', function(e) {
            if (e.target.closest('.j_headlines_favorites_make_roadmap_new')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_favorites_make_roadmap_new');
                const headlineId = button.id; // Usar o ID do elemento (primary key do registro)
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    // Verificar se já existe roteiro
                    checkExistingRoadmapNew(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado no botão ou é null/undefined');
                }
            }
        });

        function checkExistingRoadmapNew(headlineId, headlineText) {
            // Buscar se já existe roteiro
            $.ajax({
                url: "dashboard/user/roadmaps/favorites/show-favorites",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    id: headlineId
                },
                success: function(data) {
                    if (data.success && data.roadmap_engreversa) {
                        // Roteiro já existe - mostrar modal com o roteiro existente
                        showExistingRoadmapNew(headlineId, headlineText, data.roadmap_engreversa, data
                            .search_id, data.search_text);
                    } else {
                        // Roteiro não existe - criar novo
                        createRoadmapNew(headlineId);
                    }
                },
                error: function(xhr) {
                    // Em caso de erro, tentar criar novo roteiro
                    createRoadmapNew(headlineId);
                }
            });
        }

        function showExistingRoadmapNew(headlineId, headlineText, roadmapContent, searchId, searchText) {
            // Preencher o modal de visualização com o roteiro existente
            document.getElementById('viewRoadmapHeadlineNew').value = decodeURIComponent(headlineText);
            document.getElementById('viewRoadmapContentNew').value = roadmapContent;

            // Verificar se há dados de pesquisa para mostrar a aba de fontes
            if (searchId && searchText) {
                console.log('Dados de pesquisa encontrados no roteiro favorito');
                // Mostrar a aba de fontes
                document.getElementById('view-sources-tab-li').style.display = 'block';

                // Formatar e exibir o search_text
                let searchTextFormatted = searchText.replace(/\n/g, '<br>');
                document.getElementById('view-search-sources-content').innerHTML = searchTextFormatted;
            } else {
                // Esconder a aba de fontes se não houver dados
                document.getElementById('view-sources-tab-li').style.display = 'none';
                document.getElementById('view-search-sources-content').innerHTML = '';
            }

            // Abrir o modal de visualização
            const modal = new bootstrap.Modal(document.getElementById('viewRoadmapModalNew'));
            modal.show();
        }

        function recreateRoadmapNew() {
            const headlineId = document.getElementById('roadmapHeadlineIdNew').value;
            const headlineText = document.getElementById('roadmapHeadlineResultNew').value;

            // Limpar o campo de observações
            document.getElementById('roadmapContentNew').value = '';

            // Preencher o modal para recriação
            document.getElementById('roadmapHeadlineNew').value = headlineText;

            // Mostrar estado de formulário para recriar
            showRoadmapStateNew('form');
        }
    
