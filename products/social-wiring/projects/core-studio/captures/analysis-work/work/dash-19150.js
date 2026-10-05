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
    
