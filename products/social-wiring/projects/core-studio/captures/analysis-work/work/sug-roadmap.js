/* ===== SCRIPT #29 @343880 attrs= len=17895 */

        // Funções para o modal de roteiro
        function createRoadmap(headlineId) {
            console.log('Criar roteiro para headline:', headlineId);
            document.getElementById('roadmapContent').value = '';

            // Buscar a headline no DOM - usando o botão que foi clicado
            const clickedButton = document.querySelector(`[data-headline-id="${headlineId}"]`);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher o modal
            document.getElementById('roadmapHeadline').value = decodeURIComponent(headlineText);
            document.getElementById('roadmapHeadlineId').value = headlineId;

            // Mostrar estado inicial (formulário)
            showRoadmapState('form');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
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

            // AJAX para criar roteiro no backend usando endpoint correto
            $.ajax({
                url: "/dashboard/user/headlines/create-advanced-roadmap",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    headline_id: headlineId,
                    context_data: roadmapContent,
                    mode: 'default',
                    ai_provider: 'claude'
                },
                success: function(data) {
                    if (data.success) {
                        // Iniciar long polling para verificar status
                        startLongPolling(headlineId);
                        toastr.success('Roteiro enviado para processamento!');
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

        function viewRoadmap(headlineId) {
            // Buscar a headline no DOM - usando o botão que foi clicado
            const clickedButton = document.querySelector(`[data-headline-id="${headlineId}"]`);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher a headline no modal
            document.getElementById('viewRoadmapHeadline').value = decodeURIComponent(headlineText);

            // Buscar o roteiro via AJAX
            $.ajax({
                url: "/dashboard/user/roadmaps/reversa/show/" + headlineId,
                type: 'GET',
                data: {
                    headline_id: headlineId
                },
                success: function(data) {
                    if (data.success && data.roadmap_engreversa) {
                        // Preencher o roteiro no modal
                        document.getElementById('viewRoadmapContent').value = data.roadmap_engreversa;

                        // Abrir o modal
                        const modal = new bootstrap.Modal(document.getElementById('viewRoadmapModal'));
                        modal.show();
                    } else {
                        toastr.error(data.message || 'Roteiro não encontrado ou ainda não processado');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao buscar o roteiro');
                    console.error(xhr);
                }
            });
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

        // Event delegation para os botões de ação
        document.addEventListener('click', function(e) {
            if (e.target.closest('.j_headlines_suggesteds_make_roadmap')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_suggesteds_make_roadmap');
                const headlineId = button.getAttribute('data-headline-id');
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    // Verificar se já existe roteiro
                    checkExistingRoadmap(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado no botão ou é null/undefined');
                }
            }

            if (e.target.closest('.j_headlines_suggesteds_delete')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_suggesteds_delete');
                const headlineId = button.getAttribute('data-headline-id');
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    // Mostrar modal de confirmação
                    showDeleteConfirmation(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado no botão de delete');
                }
            }
        });

        function checkExistingRoadmap(headlineId, headlineText) {
            // Buscar se já existe roteiro
            $.ajax({
                url: "/dashboard/user/roadmaps/reversa/show/" + headlineId,
                type: 'GET',
                data: {
                    headline_id: headlineId
                },
                success: function(data) {
                    if (data.success && data.roadmap_engreversa && data.status === 'completed') {
                        // Roteiro já existe e está completo - mostrar modal com o roteiro existente
                        showExistingRoadmap(headlineId, headlineText, data.roadmap_engreversa);
                    } else {
                        // Roteiro não existe ou não está completo - criar novo
                        createRoadmap(headlineId);
                    }
                },
                error: function(xhr) {
                    // Em caso de erro, tentar criar novo roteiro
                    createRoadmap(headlineId);
                }
            });
        }

        function showExistingRoadmap(headlineId, headlineText, roadmapContent) {
            // Preencher o modal com o roteiro existente
            document.getElementById('roadmapHeadlineResult').value = decodeURIComponent(headlineText);
            document.getElementById('roadmapResult').value = roadmapContent;
            document.getElementById('roadmapHeadlineId').value = headlineId;

            // Mostrar estado de resultado (roteiro existente)
            showRoadmapState('result');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
            modal.show();
        }

        function recreateRoadmap() {
            const headlineId = document.getElementById('roadmapHeadlineId').value;
            const headlineText = document.getElementById('roadmapHeadlineResult').value;

            // Limpar o campo de observações
            document.getElementById('roadmapContent').value = '';

            // Preencher o modal para recriação
            document.getElementById('roadmapHeadline').value = headlineText;

            // Mostrar estado de formulário para recriar
            showRoadmapState('form');
        }

        function showDeleteConfirmation(headlineId, headlineText) {
            // Preencher o modal de confirmação
            document.getElementById('deleteHeadlineId').value = headlineId;
            document.getElementById('deleteHeadlineText').textContent = decodeURIComponent(headlineText);

            // Abrir o modal de confirmação
            const modal = new bootstrap.Modal(document.getElementById('deleteConfirmationModal'));
            modal.show();
        }

        function confirmDelete() {
            const headlineId = document.getElementById('deleteHeadlineId').value;

            if (!headlineId) {
                toastr.error('ID da headline não encontrado');
                return;
            }

            // AJAX para deletar
            $.ajax({
                url: '/dashboard/user/headlines/suggested/delete',
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    id: headlineId
                },
                success: function(data) {
                    if (data.success) {
                        toastr.success(data.message || 'Headline deletada com sucesso!');

                        // Fechar modal
                        const modal = bootstrap.Modal.getInstance(document.getElementById(
                            'deleteConfirmationModal'));
                        modal.hide();

                        // Recarregar a tabela
                        if (typeof table !== 'undefined') {
                            table.ajax.reload();
                        } else {
                            // Fallback: recarregar a página
                            window.location.reload();
                        }
                    } else {
                        toastr.error(data.message || 'Erro ao deletar headline');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao deletar headline');
                    console.error(xhr);
                }
            });
        }

        // Variáveis globais para long polling
        let pollingTimeout = null;
        let isPollingActive = false;

        function startLongPolling(headlineId) {
            let pollCount = 0;
            const maxPolls = 60; // Máximo 5 minutos (60 * 5 segundos)
            isPollingActive = true;

            function pollStatus() {
                if (!isPollingActive) {
                    return;
                }
                pollCount++;
                updateProgress(pollCount, maxPolls);

                $.ajax({
                    url: "/dashboard/user/roadmaps/reversa/show/" + headlineId,
                    type: 'GET',
                    data: {
                        headline_id: headlineId
                    },
                    success: function(data) {
                        if (data.success && data.roadmap_engreversa && data.status === 'completed') {
                            // Roteiro concluído com sucesso
                            document.getElementById('roadmapHeadlineResult').value = document.getElementById(
                                'roadmapHeadline').value;
                            document.getElementById('roadmapResult').value = data.roadmap_engreversa;
                            showRoadmapState('result');
                            toastr.success('Roteiro criado com sucesso!');
                            stopPolling();
                        } else if (data.success === false || data.status !== 'completed') {
                            // Roteiro ainda está sendo processado - continuar polling
                            if (pollCount >= maxPolls) {
                                showRoadmapState('form');
                                toastr.error(
                                    'Timeout: O roteiro está demorando mais que o esperado. Tente novamente.'
                                );
                                stopPolling();
                            } else {
                                pollingTimeout = setTimeout(pollStatus, 5000);
                            }
                        } else if (pollCount >= maxPolls) {
                            showRoadmapState('form');
                            toastr.error(
                                'Timeout: O roteiro está demorando mais que o esperado. Tente novamente.');
                            stopPolling();
                        } else {
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    },
                    error: function(xhr) {
                        if (pollCount >= maxPolls) {
                            isPollingActive = false;
                            showRoadmapState('form');
                            toastr.error('Erro ao verificar status do roteiro');
                        } else {
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    }
                });
            }
            pollingTimeout = setTimeout(pollStatus, 2000);
        }

        function updateProgress(current, max) {
            const percentage = Math.min((current / max) * 100, 100);
            document.querySelector('#creatingRoadmapState .progress-bar').style.width = percentage + '%';
            document.querySelector('#creatingRoadmapState .progress-bar').setAttribute('aria-valuenow', percentage);

            let statusText = '';
            if (current <= 6) {
                statusText = 'Iniciando processamento...';
            } else if (current <= 12) {
                statusText = 'Processando com GPT...';
            } else if (current <= 24) {
                statusText = 'Revisando com Assistant...';
            } else if (current <= 36) {
                statusText = 'Finalizando roteiro...';
            } else if (current <= 48) {
                statusText = 'Quase pronto...';
            } else {
                statusText = 'Aguarde, processamento em andamento...';
            }

            document.getElementById('progressStatus').textContent = statusText;
        }

        function stopPolling() {
            if (pollingTimeout) {
                clearTimeout(pollingTimeout);
                pollingTimeout = null;
            }
            isPollingActive = false;
        }

        function cancelRoadmapCreation() {
            stopPolling();
            showRoadmapState('form');
            toastr.info('Criação do roteiro cancelada');
        }

        // Parar polling quando modal for fechado
        document.addEventListener('hidden.bs.modal', function(e) {
            if (e.target.id === 'createRoadmapModal') {
                stopPolling();
            }
        });
    
