
        function openViralModal(id, topic) {
            // Atualiza o título do modal
            document.getElementById('viralModalLabel').textContent = `Assuntos Virais - ${topic}`;

            // Mostra o modal
            const modal = new bootstrap.Modal(document.getElementById('viralModal'));
            modal.show();

            // Busca os dados dos virais
            fetchViralData(id);
        }

        function openUserVariableModal(engReversaResultId, content) {
            const base = '/dashboard/user/library';
            if (engReversaResultId) {
                window.open(base + '?viral_result_id=' + engReversaResultId, '_blank');
            } else {
                window.open(base + '?transcription_search=' + encodeURIComponent(content), '_blank');
            }
        }

        function fetchViralDataUserVariables(id) {
            const modalContent = document.getElementById('viralModalContent');

            // Mostra loading
            modalContent.innerHTML = `
                <div class="text-center">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Carregando...</span>
                    </div>
                    <p class="mt-2">Buscando dados dos virais...</p>
                </div>
            `;

            // Faz a requisição AJAX
            fetch(`/dashboard/user/searches/user-variables-viral-data/${id}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        displayViralData(data.data);
                    } else {
                        modalContent.innerHTML = `
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-triangle"></i>
                            Erro ao carregar dados: ${data.message || 'Erro desconhecido'}
                        </div>
                    `;
                    }
                })
                .catch(error => {
                    console.error('Erro:', error);
                    modalContent.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Erro ao conectar com o servidor. Tente novamente.
                    </div>
                `;
                });
        }

        function fetchViralData(id) {
            const modalContent = document.getElementById('viralModalContent');

            // Mostra loading
            modalContent.innerHTML = `
                <div class="text-center">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Carregando...</span>
                    </div>
                    <p class="mt-2">Buscando dados dos virais...</p>
                </div>
            `;

            // Faz a requisição AJAX
            fetch(`/dashboard/user/searches/viral-data/${id}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        displayViralData(data.data);
                    } else {
                        modalContent.innerHTML = `
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-triangle"></i>
                            Erro ao carregar dados: ${data.message || 'Erro desconhecido'}
                        </div>
                    `;
                    }
                })
                .catch(error => {
                    console.error('Erro:', error);
                    modalContent.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Erro ao conectar com o servidor. Tente novamente.
                    </div>
                `;
                });
        }

        function displayViralData(viralData) {
            const modalContent = document.getElementById('viralModalContent');

            if (!viralData || viralData.length === 0) {
                modalContent.innerHTML = `
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle"></i>
                        Nenhum dado viral encontrado para este tópico.
                    </div>
                `;
                return;
            }

            let html = '<div class="row">';

            viralData.forEach((item, index) => {
                const playsFormatted = formatNumberWithSuffix(item.plays || 0);
                const likesFormatted = formatNumberWithSuffix(item.likes || 0);
                const commentsFormatted = formatNumberWithSuffix(item.comments || 0);

                // Formatar data
                let formattedDate = '-';
                if (item.post_date) {
                    const date = new Date(item.post_date);
                    formattedDate = date.toLocaleDateString('pt-BR', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric'
                    });
                }

                html += `
                    <div class="col-md-4 col-sm-6 mb-3">
                        <div class="card h-100" style="cursor: pointer;" onclick="window.open('${item.url || '#'}', '_blank')">
                            <div class="card-body p-2">
                                <div class="text-center">
                                    <img src="${item.thumbnail || '/back/static/placeholder.jpg'}"
                                         alt="Thumbnail"
                                         class="img-fluid rounded mb-2"
                                         style="width: 100%; height: 120px; object-fit: cover;">
                                </div>
                                <div class="text-center">
                                    <div class="row g-1">
                                        <div class="col-4">
                                            <div class="text-center">
                                                <div class="text-muted small">Views</div>
                                                <div class="fw-bold text-primary small">${playsFormatted}</div>
                                            </div>
                                        </div>
                                        <div class="col-4">
                                            <div class="text-center">
                                                <div class="text-muted small">Likes</div>
                                                <div class="fw-bold text-danger small">${likesFormatted}</div>
                                            </div>
                                        </div>
                                        <div class="col-4">
                                            <div class="text-center">
                                                <div class="text-muted small">Comments</div>
                                                <div class="fw-bold text-success small">${commentsFormatted}</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="mt-2">
                                        <small class="text-muted">${formattedDate}</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            modalContent.innerHTML = html;
        }

        function formatNumberWithSuffix(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
            }
            return num.toString();
        }

        // Funções para gerenciar itens pendentes das variáveis

        function approveItem(variableId, item, itemId = null) {
            const approvedTextarea = document.querySelector(`#tab-approved-${variableId} textarea`);

            if (approvedTextarea) {
                // Adicionar item ao início do textarea aprovado
                const currentContent = approvedTextarea.value.trim();
                const newContent = currentContent ? `${item}\n${currentContent}` : item;
                approvedTextarea.value = newContent;

                // Remover item da lista pendente visualmente
                // Buscar o card pelo data-item-id (agora está na div.card)
                const card = document.querySelector(`.card[data-item-id="${itemId}"]`);
                if (card) {
                    // Encontrar o container pai e remover ele (assim remove o card inteiro)
                    const parentContainer = card.closest('.pending-item-container');
                    if (parentContainer) {
                        parentContainer.remove();
                    } else {
                        // Fallback: remover apenas o card se não encontrar o container
                        card.remove();
                    }
                }

                // Se tem ID do banco, armazenar para aprovar quando salvar o formulário
                if (itemId) {
                    // Criar ou obter campo hidden para armazenar IDs dos itens aprovados
                    let approvedItemsInput = document.querySelector(`#approved-items-${variableId}`);
                    if (!approvedItemsInput) {
                        approvedItemsInput = document.createElement('input');
                        approvedItemsInput.type = 'hidden';
                        approvedItemsInput.id = `approved-items-${variableId}`;
                        approvedItemsInput.name = `approved_items[${variableId}]`;
                        approvedTextarea.parentElement.appendChild(approvedItemsInput);
                    }

                    // Adicionar ID do item à lista
                    const currentIds = approvedItemsInput.value ? approvedItemsInput.value.split(',') : [];
                    if (!currentIds.includes(itemId.toString())) {
                        currentIds.push(itemId);
                        approvedItemsInput.value = currentIds.join(',');
                    }
                }

                // Atualizar contador
                updatePendingTabCounter(variableId);

                // Mostrar notificação
                showNotification('Item movido para aprovados! Clique em Atualizar para salvar.', 'success');
            }

            $(document).trigger('pending:update');
        }

        function rejectItem(variableId, button, itemId = null) {
            if (confirm('Tem certeza que deseja excluir este item?')) {
                const itemContainer = button.closest('.pending-item-container');

                // Remover item da lista pendente visualmente
                if (itemContainer) {
                    itemContainer.remove();
                }

                // Se tem ID do banco, armazenar para excluir quando salvar o formulário
                if (itemId) {
                    const approvedTextarea = document.querySelector(`#tab-approved-${variableId} textarea`);

                    // Criar ou obter campo hidden para armazenar IDs dos itens rejeitados
                    let rejectedItemsInput = document.querySelector(`#rejected-items-${variableId}`);
                    if (!rejectedItemsInput) {
                        rejectedItemsInput = document.createElement('input');
                        rejectedItemsInput.type = 'hidden';
                        rejectedItemsInput.id = `rejected-items-${variableId}`;
                        rejectedItemsInput.name = `rejected_items[${variableId}]`;
                        approvedTextarea.parentElement.appendChild(rejectedItemsInput);
                    }

                    // Adicionar ID do item à lista
                    const currentIds = rejectedItemsInput.value ? rejectedItemsInput.value.split(',') : [];
                    if (!currentIds.includes(itemId.toString())) {
                        currentIds.push(itemId);
                        rejectedItemsInput.value = currentIds.join(',');
                    }
                }

                // Atualizar contador
                updatePendingTabCounter(variableId);

                // Mostrar notificação
                showNotification('Item marcado para exclusão! Clique em Atualizar para salvar.', 'info');
            }
        }

        function removePendingItem(variableId, button) {
            const itemContainer = button.closest('.pending-item-container');
            itemContainer.remove();
            updatePendingTabCounter(variableId);
        }

        function updatePendingTabCounter(variableId) {
            const container = document.querySelector(`#pending-items-${variableId}`);
            const items = container.querySelectorAll('.pending-item-container');
            const tabLink = document.querySelector(`a[href="#tab-pending-${variableId}"]`);

            if (items.length === 0) {
                // Mostrar mensagem de "nenhum item"
                container.innerHTML = `
                    <div class="text-muted text-center py-3">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon mb-2" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                            <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/>
                            <path d="M12 7l0 5l3 3"/>
                        </svg>
                        <p>Nenhum item pendente</p>
                    </div>
                `;

                // Remover contador do tab
                const counter = tabLink.querySelector('.badge');
                if (counter) {
                    counter.remove();
                }
            } else {
                // Atualizar ou adicionar contador
                let counter = tabLink.querySelector('.badge');
                if (!counter) {
                    counter = document.createElement('span');
                    counter.className = 'badge bg-yellow ms-1';
                    tabLink.appendChild(counter);
                }
                counter.textContent = items.length;
            }
        }


        // Função para ativar todas as tabs "Aprovado" que ainda não foram clicadas
        function activateApprovedTabs() {
            // Procurar por todas as tabs de variáveis e virais
            const allTabContainers = document.querySelectorAll('.card-body .nav.nav-tabs');

            allTabContainers.forEach(container => {
                // Verificar se nenhuma tab está ativa neste container
                const activeTabs = container.querySelectorAll('.nav-link.active');

                if (activeTabs.length === 0) {
                    // Se nenhuma tab está ativa, ativar a primeira (que geralmente é "Aprovado")
                    const firstLink = container.querySelector('.nav-link');
                    const firstTab = firstLink ? document.querySelector(firstLink.getAttribute('href')) : null;

                    if (firstLink && firstTab) {
                        firstLink.classList.add('active');
                        firstTab.classList.add('active', 'show');
                    }
                }
            });
        }

        // Função para mostrar/esconder botão Atualizar baseado na tab ativa
        function toggleUpdateButton() {
            const formFooter = document.getElementById('form-footer');
            const subjectViralTab = document.getElementById('subject-viral');
            const myResearchTab = document.getElementById('my-research');

            const shouldHide = (subjectViralTab && subjectViralTab.classList.contains('active'))
                            || (myResearchTab && myResearchTab.classList.contains('active'));

            if (formFooter) {
                formFooter.style.display = shouldHide ? 'none' : 'block';
            }
        }

        // Inicializar tabs quando a página carregar
        document.addEventListener('DOMContentLoaded', function() {
            // Ativar tabs aprovadas no carregamento
            activateApprovedTabs();

            // Verificar qual aba está ativa e mostrar/esconder botão Atualizar
            toggleUpdateButton();

            // Adicionar listener SOMENTE para as tabs principais (Me, Público, Assuntos Virais)
            // Mas NÃO para tabs internas de assuntos virais para evitar reload
            const mainTabLinks = document.querySelectorAll('.card-header-tabs > li > a[data-bs-toggle="tab"]');
            mainTabLinks.forEach(tabLink => {
                // Verificar se não é uma tab interna de assuntos virais
                const href = tabLink.getAttribute('href');
                if (href && !href.includes('tab-pending-viral-topics') && !href.includes(
                        'tab-approved-viral-topics')) {
                    tabLink.addEventListener('shown.bs.tab', function(e) {
                        // Pequeno delay para garantir que o Bootstrap terminou de renderizar
                        setTimeout(() => {
                            activateApprovedTabs();
                            toggleUpdateButton(); // Atualiza a visibilidade do botão
                        }, 50);
                    });
                }
            });

            // Event listener para o botão de confirmação de remoção do tópico viral
            const removeConfirmBtn = document.getElementById('viral_topic_remove_confirm');
            if (removeConfirmBtn) {
                removeConfirmBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    const id = this.getAttribute('data-id');
                    if (id) {
                        removeViralTopic(id);
                    }
                });
            }

            // ========== EVENT LISTENERS PARA APROVAR/REPROVAR TÓPICOS VIRAIS PENDENTES ==========
            // Botões de aprovar/reprovar agora chamam diretamente handleViralAction via onclick
            // Não precisa mais de modais ou event listeners adicionais
        });

        // Função para mostrar notificações
        function showNotification(message, type) {
            const alertClass = type === 'success' ? 'alert-success' : type === 'error' ? 'alert-danger' : 'alert-info';
            const notification = document.createElement('div');
            notification.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
            notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
            notification.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;

            document.body.appendChild(notification);

            // Remover automaticamente após 3 segundos
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 3000);
        }

        // ========== FUNÇÕES GLOBAIS PARA VARIÁVEIS (Declaradas apenas uma vez) ==========

        // Controle para evitar múltiplas chamadas simultâneas
        const loadingStates = {};

        async function loadTabVariables(type) {
            if (type === 'unified') {
                // loadUnifiedData is defined in a later script block; defer to ensure it's available
                setTimeout(async () => {
                    if (typeof loadUnifiedData === 'function') {
                        await loadUnifiedData();
                    }
                }, 0);
                return;
            }
            // Verifica se já está carregando este tipo
            if (loadingStates[type]) {
                console.log(`Já está carregando dados para o tipo: ${type}`);
                return;
            }

            const loadingElement = document.getElementById('global-variables-loading');
            const contentElement = document.getElementById('variables-content');

            try {
                // Marca como carregando
                loadingStates[type] = true;

                const response = await fetch(`/dashboard/user/searches/variables/items?type=${type}`);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || 'Erro ao carregar');
                }
                console.log(result);
                Object.keys(result.data).forEach(variableId => {
                    const data = result.data[variableId];
                    renderApprovedItems(variableId, data.approved_manual, data.approved);
                    renderPendingItemsAjax(variableId, data.pending);
                });

                if (loadingElement) loadingElement.style.display = 'none';
                if (contentElement) contentElement.style.display = 'block';

            } catch (error) {
                console.error('Erro:', error);
                if (loadingElement) {
                    loadingElement.innerHTML = `
                        <div class="alert alert-danger" role="alert" style="max-width: 600px; margin: 0 auto;">
                            <div class="d-flex">
                                <div>
                                    <svg xmlns="http://www.w3.org/2000/svg" class="icon alert-icon" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                        <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                        <path d="M12 9v4"/>
                                        <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z"/>
                                        <path d="M12 16h.01"/>
                                    </svg>
                                </div>
                                <div>
                                    <h4 class="alert-title">Erro ao carregar</h4>
                                    <div class="text-secondary">${error.message}</div>
                                    <button class="btn btn-primary mt-3" onclick="location.reload()">Tentar novamente</button>
                                </div>
                            </div>
                        </div>
                    `;
                }
            } finally {
                // Limpa o estado de carregamento
                loadingStates[type] = false;
            }
        }

        window._mainGroupData = window._mainGroupData || {};

        function renderApprovedItems(variableId, approvedManual, approved) {
            window._mainGroupData[variableId] = {
                approvedManual: approvedManual || [],
                approved: approved || [],
            };
            _renderApprovedItemsFromData(variableId);
        }

        function _renderApprovedItemsFromData(variableId) {
            const container = document.getElementById(`approved-items-${variableId}`);
            if (!container) return;

            const data = window._mainGroupData[variableId] || { approvedManual: [], approved: [] };
            let html = '';

            data.approvedManual.forEach(item => {
                html += renderApprovedManualItem(variableId, item);
            });

            data.approved.forEach(item => {
                html += renderApprovedPendingItem(variableId, item);
            });

            if (html === '') {
                html = `
                    <div class="text-muted text-center py-3">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon mb-2" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                            <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                            <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                            <path d="M12 7l0 5l3 3" />
                        </svg>
                        <p>Nenhum item aprovado</p>
                    </div>
                `;
            }

            container.innerHTML = html;
        }

        function sortMainGroup(variableId, sortType, btn) {
            const data = window._mainGroupData[variableId];
            if (!data) return;

            document.querySelectorAll(`.main-sort-btn-${variableId}`).forEach(b => {
                b.style.background = 'transparent';
                b.style.color = '#c084fc';
                b.style.borderColor = '#9945FF44';
            });
            btn.style.background = 'linear-gradient(135deg, #7c3aed, #9945FF)';
            btn.style.color = '#fff';
            btn.style.borderColor = 'transparent';

            if (sortType === 'plays') {
                data.approved = [...data.approved].sort((a, b) => (b.plays || 0) - (a.plays || 0));
            } else {
                data.approved = [...data.approved].sort((a, b) => b.id - a.id);
            }

            _renderApprovedItemsFromData(variableId);
        }

        function renderApprovedManualItem(variableId, item) {
            const source = item.source || 'content';
            return `
                <div class="pending-item-container mb-3">
                    <div class="card border-primary bg-primary-lt" data-item-id="${item.id}" data-source="${source}"
                        style="background: #9945FF33 !important; border: 1.25px solid #9945FF !important; color: #E1C8FF !important;
                        border-radius: 8px !important;">
                        <div class="card-body p-3 d-flex justify-content-between">
                            <div class="d-flex align-items-center justify-content-between flex-grow-1">
                                <div class="form-check mb-0">
                                    <input class="form-check-input item-checkbox-approved-${variableId}"
                                        type="checkbox" value="${item.id}" id="checkbox-approved-${variableId}-${item.id}"
                                        data-source="${source}"
                                        onchange="updateDeleteButton('approved', ${variableId})">
                                </div>
                                <div class="d-flex align-items-center flex-grow-1">
                                    <span class="badge bg-primary me-2 text-white" style="height: 24px; display: inline-flex; align-items: center; justify-content: center">
                                        ${item.content}
                                    </span>
                                    <span id="user-variables-views" style="height: 24px; display: inline-flex;
                                        align-items: center; justify-content: center; background: rgba(59, 92, 255, 1) !important;">
                                        Manual
                                    </span>
                                    <small class="" style="color: rgba(166, 181, 255, 1)">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="icon me-1" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                            <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                                            <path d="M12 7l0 5l3 3" />
                                        </svg>
                                        Aprovado
                                    </small>
                                </div>
                            </div>
                            <button type="button" class="btn btn-outline-danger btn-sm d-flex align-items-center remove-item-btn p-0 d-flex
                                align-items-center justify-content-center btn-sm-2-custom" title="Excluir item"
                                data-variable-id="${variableId}" data-item-id="${item.id}" data-source="${source}">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon m-0 p-0" viewBox="0 0 24 24" stroke-width="2"
                                    stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"
                                    style="height: 15px; width: 15px">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                    <path d="M4 7l16 0"/>
                                    <path d="M10 11l0 6"/>
                                    <path d="M14 11l0 6"/>
                                    <path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/>
                                    <path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }

        function renderApprovedPendingItem(variableId, item) {
            const playsHtml = item.plays ? `
                <span class="badge bg-primary me-2 text-white" style="height: 24px; display: inline-flex; align-items: center; justify-content: center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="icon me-1" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                        <path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" />
                        <path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6" />
                    </svg>
                    ${formatNumber(item.plays)} views
                </span>
            ` : '';

            const source = item.source || 'pending';
            return `
                <div class="pending-item-container mb-3">
                    <div class="card border-primary bg-primary-lt" data-item-id="${item.id}" data-source="${source}"
                        style="background: #9945FF33 !important; border: 1.25px solid #9945FF !important; color: #E1C8FF !important;
                        border-radius: 8px !important;">
                        <div class="card-body p-3 d-flex justify-content-between">
                            <div class="d-flex align-items-center justify-content-between flex-grow-1">
                                <div class="form-check mb-0">
                                    <input class="form-check-input item-checkbox-approved-${variableId}" type="checkbox" value="${item.id}" id="checkbox-approved-${variableId}-${item.id}" data-source="${source}" onchange="updateDeleteButton('approved', ${variableId})">
                                </div>
                                <div class="d-flex align-items-center justify-content-between flex-grow-1" style="cursor: pointer;" onclick="openUserVariableModal(${item.eng_reversa_result_id || 0}, '${item.content}')">
                                <div class="d-flex align-items-center flex-grow-1">
                                    <span class="badge bg-primary me-2 text-white" style="height: 24px; display: inline-flex; align-items: center; justify-content: center">
                                        ${item.content}
                                    </span>
                                    ${playsHtml}
                                    <small class="" style="color: rgba(166, 181, 255, 1)">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="icon me-1" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                            <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                                            <path d="M12 7l0 5l3 3" />
                                        </svg>
                                        Aprovado
                                    </small>
                                    </div>
                                </div>
                            </div>
                            <button type="button" class="btn btn-outline-danger btn-sm d-flex align-items-center remove-item-btn p-0 d-flex
                                align-items-center justify-content-center btn-sm-2-custom" title="Excluir item" data-variable-id="${variableId}"
                                data-item-id="${item.id}" data-source="${source}">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon m-0 p-0" viewBox="0 0 24 24" stroke-width="2"
                                    stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"
                                    style="height: 15px; width: 15px">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                    <path d="M4 7l16 0"/>
                                    <path d="M10 11l0 6"/>
                                    <path d="M14 11l0 6"/>
                                    <path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/>
                                    <path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/>
                                </svg>
                            </button>

                        </div>
                    </div>
                </div>
            `;
        }

        window._mainPendingGroupData = window._mainPendingGroupData || {};

        function renderPendingItemsAjax(variableId, pending) {
            window._mainPendingGroupData[variableId] = pending || [];
            _renderPendingItemsFromData(variableId);
        }

        function _renderPendingItemsFromData(variableId) {
            const container = document.getElementById(`pending-items-${variableId}`);
            if (!container) return;

            const pending = window._mainPendingGroupData[variableId] || [];
            let html = '';

            const badge = document.querySelector(`.pending-count-badge-${variableId}`);
            if (badge) {
                if (pending.length > 0) {
                    badge.textContent = pending.length;
                    badge.style.display = '';
                } else {
                    badge.style.display = 'none';
                }
            }

            if (pending.length > 0) {
                pending.forEach(item => {
                    html += renderPendingItemCard(variableId, item);
                });
            } else {
                html = `
                    <div class="text-muted text-center py-3">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon mb-2" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                            <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                            <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                            <path d="M12 7l0 5l3 3" />
                        </svg>
                        <p>Nenhum item pendente</p>
                    </div>
                `;
            }

            container.innerHTML = html;
        }

        function sortMainPendingGroup(variableId, sortType, btn) {
            const data = window._mainPendingGroupData[variableId];
            if (!data) return;

            document.querySelectorAll(`.main-pending-sort-btn-${variableId}`).forEach(b => {
                b.style.background = 'transparent';
                b.style.color = '#c084fc';
                b.style.borderColor = '#9945FF44';
            });
            btn.style.background = 'linear-gradient(135deg, #7c3aed, #9945FF)';
            btn.style.color = '#fff';
            btn.style.borderColor = 'transparent';

            if (sortType === 'plays') {
                window._mainPendingGroupData[variableId] = [...data].sort((a, b) => (b.plays || 0) - (a.plays || 0));
            } else {
                window._mainPendingGroupData[variableId] = [...data].sort((a, b) => b.id - a.id);
            }

            _renderPendingItemsFromData(variableId);
        }

        function renderPendingItemCard(variableId, item) {
            const playsHtml = item.plays ? `
                <span class="badge bg-primary me-2 text-white">
                    <svg xmlns="http://www.w3.org/2000/svg" class="icon me-1" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                        <path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" />
                        <path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6" />
                    </svg>
                    ${formatNumber(item.plays)} views
                </span>
            ` : '';

            const source = 'pending'; // Itens pendentes sempre vêm de UserVariablePending
            return `
                <div class="pending-item-container mb-3">
                    <div class="card border-warning bg-warning-lt" data-item-id="${item.id}" data-source="${source}"
                        style="background: #ffa60017 !important; border: 1.25px solid #ff9900ff !important; color: #ffffffff !important;
                        border-radius: 8px !important;">
                        <div class="card-body p-3">
                            <div class="d-flex align-items-center justify-content-between">
                                <div class="d-flex align-items-center flex-grow-1">
                                    <div class="form-check mb-0">
                                        <input class="form-check-input item-checkbox-pending-${variableId}" type="checkbox" value="${item.id}" id="checkbox-pending-${variableId}-${item.id}" data-source="${source}" onchange="updateDeleteButton('pending', ${variableId})">
                                    </div>
                                    <span class="badge me-2 text-white d-flex align-items-center justify-content-center" style="height: 24px; background-color: #ff9900ff">
                                        ${item.content}
                                    </span>
                                    ${playsHtml}
                                    <small class="text-muted">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="icon me-1" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                            <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                                            <path d="M12 7l0 5l3 3" />
                                        </svg>
                                        Pendente
                                    </small>
                                </div>
                                <div class="d-flex gap-2">
                                    <button type="button" class="btn btn-sm d-flex align-items-center btn-sm-2-custom"
                                        onclick="openUserVariableModal(${item.eng_reversa_result_id || 0}, '${item.content}')" title="Ver na biblioteca"
                                        style="background-color: #3B5CFF; color: #fff; border: 1px solid #FFFFFF33">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="icon m-0 p-0" viewBox="0 0 24 24" stroke-width="2"
                                            stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"
                                            style="height: 15px; width: 15px">
                                            <path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"></path>
                                            <circle cx="12" cy="12" r="3"></circle>
                                        </svg>
                                    </button>
                                    <button type="button" class="btn btn-outline-blue btn-sm d-flex align-items-center btn-sm-2-custom" onclick="setAttributeApprove(${item.id})"
                                        data-bs-toggle="modal" data-bs-target="#modal-approved-variable" title="Aprovar item">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="icon m-0 p-0" viewBox="0 0 24 24" stroke-width="2"
                                            stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"
                                            style="height: 15px; width: 15px">
                                            <path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/>
                                        </svg>
                                    </button>
                                    <button type="button" class="btn btn-outline-danger btn-sm d-flex align-items-center btn_reject_user_variable btn-sm-2-custom"
                                        onclick="setAttributeReject(${item.id})" data-bs-toggle="modal"
                                        data-bs-target="#modal-rejected-variable" title="Excluir item">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="icon m-0 p-0" viewBox="0 0 24 24" stroke-width="2"
                                            stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"
                                            style="height: 15px; width: 15px">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                            <path d="M4 7l16 0"/>
                                            <path d="M10 11l0 6"/>
                                            <path d="M14 11l0 6"/>
                                            <path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/>
                                            <path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/>
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        function formatNumber(num) {
            if (!num) return '0';
            return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
        }

        async function openExtractViralProfileModal() {
            const modalElement = document.getElementById('extractViralProfileModal');

            if (!modalElement) {
                console.error('Modal extractViralProfileModal não encontrado no DOM');
                toastr.error('Erro: Modal não encontrado. Recarregue a página.');
                return;
            }

            // Verificar se já existe uma instância do modal e removê-la
            const existingModal = bootstrap.Modal.getInstance(modalElement);
            if (existingModal) {
                existingModal.dispose();
            }

            // Criar nova instância do modal
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true
            });

            // Garantir z-index correto
            modalElement.style.zIndex = '1055';

            modal.show();

            const loading = document.getElementById('extract-profiles-loading');
            const content = document.getElementById('extract-profiles-content');
            const empty = document.getElementById('extract-profiles-empty');
            const container = document.getElementById('profiles-container');

            if (!loading || !content || !empty || !container) {
                console.error('Elementos do modal não encontrados');
                return;
            }

            // Resetar estados
            loading.style.display = 'flex';
            content.style.display = 'none';
            empty.style.display = 'none';
            container.innerHTML = '';

            // Limpar busca
            const searchInput = document.getElementById('profile-search-input');
            if (searchInput) {
                searchInput.value = '';
            }
            window.profileSearchTerm = '';
            window.currentProfilePage = 1;
            window.selectedNicheIds = [];
            window.selectedProfessionIds = [];

            // Inicializar TomSelects após um pequeno delay para garantir que o modal está renderizado
            setTimeout(async () => {
                initializeProfileFilters();

                // Buscar e pré-selecionar nichos e profissões do usuário
                try {
                    const userFiltersResponse = await fetch('/dashboard/user/profile/get-niches-professions', {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                        }
                    });

                    const userFiltersData = await userFiltersResponse.json();

                    if (userFiltersData.success && userFiltersData.data) {
                        const nicheIds = userFiltersData.data.niches || [];
                        const professionIds = userFiltersData.data.professions || [];

                        // Aguardar um pouco mais para garantir que os TomSelects foram inicializados
                        // e que os perfis já foram carregados
                        setTimeout(() => {
                            if (nicheIds.length > 0 && window.profileNicheSelect) {
                                window.profileNicheSelect.setValue(nicheIds, true);
                                window.selectedNicheIds = nicheIds;
                            }

                            if (professionIds.length > 0 && window.profileProfessionSelect) {
                                window.profileProfessionSelect.setValue(professionIds, true);
                                window.selectedProfessionIds = professionIds;
                            }

                            updateClearButtonState();

                            // Se houver filtros aplicados e perfis carregados, renderizar os perfis filtrados
                            if ((nicheIds.length > 0 || professionIds.length > 0) && window.allProfiles && window.allProfiles.length > 0) {
                                renderProfiles();
                            }
                        }, 500);
                    }
                } catch (error) {
                    console.warn('Erro ao buscar nichos e profissões do usuário:', error);
                }
            }, 100);

            try {
                const response = await fetch('/dashboard/user/searches/approved-profiles', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                            'content')
                    }
                });

                const data = await response.json();

                if (data.success && data.data && data.data.length > 0) {
                    // Armazenar todos os perfis em uma variável global para filtro e paginação
                    window.allProfiles = data.data;
                    window.currentProfilePage = 1;
                    window.profilesPerPage = 12;
                    window.profileSearchTerm = '';

                    renderProfiles();
                    updateClearButtonState();
                    loading.style.display = 'none';
                    content.style.display = 'block';
                } else {
                    loading.style.display = 'none';
                    empty.style.display = 'block';
                }
            } catch (error) {
                console.error('Erro ao buscar perfis:', error);
                loading.style.display = 'none';
                empty.style.display = 'block';
                toastr.error('Erro ao carregar perfis. Tente novamente.');
            }
        }

        // Variáveis globais para perfis
        window.allProfiles = [];
        window.currentProfilePage = 1;
        window.profilesPerPage = 12;
        window.profileSearchTerm = '';
        window.selectedNicheIds = [];
        window.selectedProfessionIds = [];
        window.profileNicheSelect = null;
        window.profileProfessionSelect = null;

        // Função para atualizar o estado visual do botão de limpar
        function updateClearButtonState() {
            const clearButtons = document.querySelectorAll('.btn-outline-danger[onclick="clearProfileSearch()"]');
            const hasFilters = window.profileSearchTerm ||
                              (window.selectedNicheIds && window.selectedNicheIds.length > 0) ||
                              (window.selectedProfessionIds && window.selectedProfessionIds.length > 0);

            clearButtons.forEach(btn => {
                if (hasFilters) {
                    btn.classList.add('has-filters');
                } else {
                    btn.classList.remove('has-filters');
                }
            });
        }

        // Inicializar TomSelects para filtros de nichos e profissões
        function initializeProfileFilters() {
            // Verificar se TomSelect está disponível
            if (typeof TomSelect === 'undefined') {
                console.warn('TomSelect não está disponível ainda. Tentando novamente...');
                setTimeout(initializeProfileFilters, 100);
                return;
            }

            // Destruir instâncias existentes se houver
            if (window.profileNicheSelect) {
                window.profileNicheSelect.destroy();
            }
            if (window.profileProfessionSelect) {
                window.profileProfessionSelect.destroy();
            }

            // Verificar se os elementos existem
            const nicheSelect = document.getElementById('profile-filter-niche');
            const professionSelect = document.getElementById('profile-filter-profession');

            if (!nicheSelect || !professionSelect) {
                console.warn('Elementos de filtro não encontrados. Tentando novamente...');
                setTimeout(initializeProfileFilters, 100);
                return;
            }

            // TomSelect para filtro de nichos
            window.profileNicheSelect = new TomSelect('#profile-filter-niche', {
                copyClassesToDropdown: false,
                dropdownParent: 'body',
                create: false,
                placeholder: 'Selecione os nichos...',
                onChange: function(values) {
                    window.selectedNicheIds = values || [];
                    window.currentProfilePage = 1;
                    updateClearButtonState();
                    renderProfiles();
                },
                render: {
                    option: function(data, escape) {
                        const tooltip = data.content || data.text;
                        return `<div class="option" title="${escape(tooltip)}">${escape(data.text)}</div>`;
                    }
                }
            });

            // TomSelect para filtro de profissões
            window.profileProfessionSelect = new TomSelect('#profile-filter-profession', {
                copyClassesToDropdown: false,
                dropdownParent: 'body',
                create: false,
                placeholder: 'Selecione as profissões...',
                onChange: function(values) {
                    window.selectedProfessionIds = values || [];
                    window.currentProfilePage = 1;
                    updateClearButtonState();
                    renderProfiles();
                },
                render: {
                    option: function(data, escape) {
                        const tooltip = data.content || data.text;
                        return `<div class="option" title="${escape(tooltip)}">${escape(data.text)}</div>`;
                    }
                }
            });
        }

        function filterProfiles() {
            const searchInput = document.getElementById('profile-search-input');
            if (searchInput) {
                window.profileSearchTerm = searchInput.value.toLowerCase().trim();
                window.currentProfilePage = 1; // Resetar para a primeira página ao filtrar
                updateClearButtonState();
                renderProfiles();
            }
        }

        function clearProfileSearch() {
            const searchInput = document.getElementById('profile-search-input');
            if (searchInput) {
                searchInput.value = '';
                window.profileSearchTerm = '';
            }

            // Limpar filtros de nichos e profissões
            if (window.profileNicheSelect) {
                window.profileNicheSelect.clear();
            }
            if (window.profileProfessionSelect) {
                window.profileProfessionSelect.clear();
            }

            window.selectedNicheIds = [];
            window.selectedProfessionIds = [];
            window.currentProfilePage = 1;
            updateClearButtonState();
            renderProfiles();
        }

        function changeProfilePage(page) {
            window.currentProfilePage = page;
            renderProfiles();
            // Scroll para o topo do container
            const container = document.getElementById('profiles-container');
            if (container) {
                container.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        }

        function renderProfiles() {
            const container = document.getElementById('profiles-container');
            const paginationContainer = document.getElementById('profiles-pagination');

            if (!container || !window.allProfiles || window.allProfiles.length === 0) {
                container.innerHTML = '';
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            // Filtrar perfis pelo termo de busca, nichos e profissões
            let filteredProfiles = window.allProfiles;

            // Filtro por nome
            if (window.profileSearchTerm) {
                filteredProfiles = filteredProfiles.filter(profile => {
                    const profileName = (profile.profile || '').toLowerCase();
                    return profileName.includes(window.profileSearchTerm);
                });
            }

            // Filtro por nichos
            if (window.selectedNicheIds && window.selectedNicheIds.length > 0) {
                filteredProfiles = filteredProfiles.filter(profile => {
                    if (!profile.niche_ids || profile.niche_ids.length === 0) {
                        return false;
                    }
                    // Verificar se pelo menos um nicho selecionado está nos nichos do perfil
                    return window.selectedNicheIds.some(nicheId =>
                        profile.niche_ids.includes(parseInt(nicheId))
                    );
                });
            }

            // Filtro por profissões
            if (window.selectedProfessionIds && window.selectedProfessionIds.length > 0) {
                filteredProfiles = filteredProfiles.filter(profile => {
                    if (!profile.profession_ids || profile.profession_ids.length === 0) {
                        return false;
                    }
                    // Verificar se pelo menos uma profissão selecionada está nas profissões do perfil
                    return window.selectedProfessionIds.some(professionId =>
                        profile.profession_ids.includes(parseInt(professionId))
                    );
                });
            }

            // Se não houver resultados após o filtro
            if (filteredProfiles.length === 0) {
                let message = 'Nenhum perfil encontrado';
                const filters = [];
                if (window.profileSearchTerm) {
                    filters.push(`com o termo "${window.profileSearchTerm}"`);
                }
                if (window.selectedNicheIds && window.selectedNicheIds.length > 0) {
                    filters.push(`com os nichos selecionados`);
                }
                if (window.selectedProfessionIds && window.selectedProfessionIds.length > 0) {
                    filters.push(`com as profissões selecionadas`);
                }
                if (filters.length > 0) {
                    message += ' ' + filters.join(' e ');
                }
                message += '.';

                container.innerHTML = `
                    <div class="col-12 text-center py-5">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-lg text-muted mb-3" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                            <path d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"/>
                            <path d="M21 21l-6 -6"/>
                        </svg>
                        <p class="text-muted">${message}</p>
                    </div>
                `;
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            // Calcular paginação
            const totalPages = Math.ceil(filteredProfiles.length / window.profilesPerPage);
            const startIndex = (window.currentProfilePage - 1) * window.profilesPerPage;
            const endIndex = startIndex + window.profilesPerPage;
            const paginatedProfiles = filteredProfiles.slice(startIndex, endIndex);

            container.innerHTML = '';

            paginatedProfiles.forEach(profile => {
                const profileCard = document.createElement('div');
                profileCard.className = 'col-md-6 col-lg-4 mb-4';

                // Renderizar thumbnails
                let thumbnailsHtml = '';
                if (profile.thumbnails && profile.thumbnails.length > 0) {
                    profile.thumbnails.forEach((thumb, index) => {
                        thumbnailsHtml += `
                            <div class="thumbnail-item" style="flex: 1; min-width: 0;">
                                <img src="${thumb}" alt="Thumbnail ${index + 1}"
                                     class="img-fluid rounded"
                                     style="width: 100%; height: 120px; object-fit: cover; cursor: pointer;"
                                     onerror="this.src='/back/static/placeholder.jpg'">
                            </div>
                        `;
                    });
                }

                // Adicionar placeholders se tiver menos de 3 thumbnails
                const missingThumbnails = 3 - (profile.thumbnails ? profile.thumbnails.length : 0);
                for (let i = 0; i < missingThumbnails; i++) {
                    thumbnailsHtml += `
                        <div class="thumbnail-item" style="flex: 1; min-width: 0; background: #f3f4f6; border-radius: 4px; display: flex; align-items: center; justify-content: center;">
                            <svg xmlns="http://www.w3.org/2000/svg" class="icon text-muted" width="32" height="32" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                <path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/>
                                <path d="M4 8l4 -4l4 4l4 -4l4 4"/>
                            </svg>
                        </div>
                    `;
                }

                const socialIcon = profile.social === 'instagram' ?
                    '<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 4m0 4a4 4 0 0 1 4 -4h8a4 4 0 0 1 4 4v8a4 4 0 0 1 -4 4h-8a4 4 0 0 1 -4 -4z"/><path d="M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"/><path d="M16.5 7.5l0 .01"/></svg>' :
                    '<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 2m0 4a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v4a4 4 0 0 1 -4 4h-4a4 4 0 0 1 -4 -4z"/><path d="M9 18m0 4a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v4a4 4 0 0 1 -4 4h-4a4 4 0 0 1 -4 -4z"/><path d="M9 10m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"/></svg>';

                profileCard.innerHTML = `
                    <div class="card h-100" style="transition: transform 0.2s, box-shadow 0.2s; position: relative;"
                         onmouseover="this.style.transform='translateY(-4px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)'"
                         onmouseout="this.style.transform=''; this.style.boxShadow=''">
                        <div class="card-body p-3">
                            <div class="d-flex align-items-center mb-3">
                                <div class="me-2">
                                    ${socialIcon}
                                </div>
                                <h5 class="card-title mb-0 flex-grow-1">@${profile.profile}</h5>
                            </div>

                            <div class="thumbnails-container mb-3" style="display: flex; gap: 4px; height: 120px;">
                                ${thumbnailsHtml}
                            </div>

                            <div class="d-flex gap-2 mt-1">
                                <a href="/dashboard/user/library?profile=${profile.profile}"
                                   target="_blank"
                                   title="Ver vídeos deste perfil"
                                   style="flex:1;display:flex;align-items:center;justify-content:center;gap:5px;height:36px;border-radius:20px;font-size:0.78rem;font-weight:600;text-decoration:none;background:linear-gradient(135deg,#6d28d9,#7c3aed);color:#fff;border:none;transition:opacity .2s;"
                                   onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                        <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                        <path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0"/>
                                        <path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6"/>
                                    </svg>
                                    Vídeos
                                </a>
                                <button type="button" 
                                        onclick="extractProfileData('${profile.profile}', '${profile.social}', ${profile.eng_reversa_search_id})"
                                        title="Extrair pesquisa deste perfil"
                                        style="flex:1;display:flex;align-items:center;justify-content:center;gap:5px;height:36px;border-radius:20px;font-size:0.78rem;font-weight:600;background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff;border:none;cursor:pointer;transition:opacity .2s;
                                        display:none"
                                        onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                        <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                        <path d="M12 5l0 14"/>
                                        <path d="M5 12l14 0"/>
                                    </svg>
                                    Extrair
                                </button>
                                <button type="button"
                                        onclick="openProfileViralSearch('${profile.profile}', ${profile.eng_reversa_search_id})"
                                        title="Ver pesquisa extraída deste perfil"
                                        style="flex:1;display:flex;align-items:center;justify-content:center;gap:5px;height:36px;border-radius:20px;font-size:0.78rem;font-weight:600;background:linear-gradient(135deg,#0d9488,#14b8a6);color:#fff;border:none;cursor:pointer;transition:opacity .2s;"
                                        onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                        <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                        <path d="M9 5h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2h-2"/>
                                        <path d="M9 3m0 2a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v0a2 2 0 0 1 -2 2h-2a2 2 0 0 1 -2 -2z"/>
                                        <path d="M9 12l.01 0"/><path d="M13 12l2 0"/>
                                        <path d="M9 16l.01 0"/><path d="M13 16l2 0"/>
                                    </svg>
                                    Pesquisa
                                </button>
                            </div>
                        </div>
                    </div>
                `;

                container.appendChild(profileCard);
            });

            // Renderizar paginação
            if (totalPages > 1 && paginationContainer) {
                let paginationHtml = '<nav aria-label="Paginação de perfis"><ul class="pagination mb-0">';

                // Botão anterior
                if (window.currentProfilePage > 1) {
                    paginationHtml += `
                        <li class="page-item">
                            <a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${window.currentProfilePage - 1})" aria-label="Anterior">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                    <path d="M15 6l-6 6l6 6"/>
                                </svg>
                            </a>
                        </li>
                    `;
                } else {
                    paginationHtml += `
                        <li class="page-item disabled">
                            <span class="page-link" aria-label="Anterior">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                    <path d="M15 6l-6 6l6 6"/>
                                </svg>
                            </span>
                        </li>
                    `;
                }

                // Números das páginas
                let startPage = Math.max(1, window.currentProfilePage - 2);
                let endPage = Math.min(totalPages, window.currentProfilePage + 2);

                if (startPage > 1) {
                    paginationHtml +=
                        `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(1)">1</a></li>`;
                    if (startPage > 2) {
                        paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
                    }
                }

                for (let i = startPage; i <= endPage; i++) {
                    if (i === window.currentProfilePage) {
                        paginationHtml += `<li class="page-item active"><span class="page-link">${i}</span></li>`;
                    } else {
                        paginationHtml +=
                            `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${i})">${i}</a></li>`;
                    }
                }

                if (endPage < totalPages) {
                    if (endPage < totalPages - 1) {
                        paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
                    }
                    paginationHtml +=
                        `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${totalPages})">${totalPages}</a></li>`;
                }

                // Botão próximo
                if (window.currentProfilePage < totalPages) {
                    paginationHtml += `
                        <li class="page-item">
                            <a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${window.currentProfilePage + 1})" aria-label="Próximo">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                    <path d="M9 6l6 6l-6 6"/>
                                </svg>
                            </a>
                        </li>
                    `;
                } else {
                    paginationHtml += `
                        <li class="page-item disabled">
                            <span class="page-link" aria-label="Próximo">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                    <path d="M9 6l6 6l-6 6"/>
                                </svg>
                            </span>
                        </li>
                    `;
                }

                paginationHtml += '</ul></nav>';

                // Adicionar informações de paginação
                const showingStart = startIndex + 1;
                const showingEnd = Math.min(endIndex, filteredProfiles.length);
                paginationHtml += `
                    <div class="text-center mt-2 text-muted small">
                        Mostrando ${showingStart}-${showingEnd} de ${filteredProfiles.length} perfil(is)
                        ${window.profileSearchTerm ? `filtrado(s) por "${window.profileSearchTerm}"` : ''}
                    </div>
                `;

                paginationContainer.innerHTML = paginationHtml;
                paginationContainer.style.display = 'flex';
            } else if (paginationContainer) {
                paginationContainer.style.display = 'none';
            }
        }

        async function extractProfileData(profile, social, engReversaSearchId) {
            // Determinar o tipo baseado na tab ativa
            const activeTab = document.querySelector('.tab-pane.active[data-type]');
            let type = null;

            if (activeTab) {
                const tabType = activeTab.getAttribute('data-type');
                if (tabType === 'avatar') {
                    type = 'myPublic';
                } else if (activeTab.id === 'subject-viral') {
                    type = 'topic_virais';
                }
            }

            // Se não conseguiu determinar o tipo, verificar pela URL ou tab visível
            if (!type) {
                const publicTab = document.getElementById('public');
                const viralTab = document.getElementById('subject-viral');

                if (publicTab && publicTab.classList.contains('active')) {
                    type = 'myPublic';
                } else if (viralTab && viralTab.classList.contains('active')) {
                    type = 'topic_virais';
                } else {
                    toastr.error('Não foi possível determinar o tipo de extração. Por favor, selecione uma tab.');
                    return;
                }
            }

            // Encontrar o card do perfil pelo nome
            const profileCards = document.querySelectorAll('.col-md-6.col-lg-4.mb-4');
            let targetCard = null;

            profileCards.forEach(card => {
                const profileName = card.querySelector('.card-title');
                if (profileName && profileName.textContent.includes(`@${profile}`)) {
                    targetCard = card.querySelector('.card');
                }
            });

            if (!targetCard) {
                toastr.error('Perfil não encontrado.');
                return;
            }

            // Criar overlay
            const overlay = document.createElement('div');
            overlay.className = 'extract-overlay';
            overlay.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: rgba(0, 0, 0, 0.7);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10;
                border-radius: 4px;
            `;

            overlay.innerHTML = `
                <div class="text-center text-white">
                    <div class="spinner-border spinner-border-lg mb-2" role="status" style="width: 3rem; height: 3rem; border-width: 0.3em;">
                        <span class="visually-hidden">Extraindo...</span>
                    </div>
                    <div class="fw-bold">Extraindo dados...</div>
                    <small class="text-white-50">@${profile}</small>
                </div>
            `;

            // Adicionar posição relativa ao card se não tiver
            if (getComputedStyle(targetCard).position === 'static') {
                targetCard.style.position = 'relative';
            }

            // Adicionar overlay
            targetCard.appendChild(overlay);

            try {
                // Fazer requisição para extrair
                const response = await fetch('/dashboard/user/searches/extract-profile', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                            'content')
                    },
                    body: JSON.stringify({
                        type: type,
                        eng_reversa_search_id: engReversaSearchId
                    })
                });

                const data = await response.json();

                async function pollExtractProfileJob(jobId) {
                    const maxPolls = 60; // ~5 minutos

                    for (let pollCount = 0; pollCount < maxPolls; pollCount++) {
                        const pollResponse = await fetch(`/dashboard/user/searches/extract-profile-status/${jobId}`, {
                            method: 'GET',
                            headers: {
                                'Content-Type': 'application/json'
                            }
                        });

                        const pollData = await pollResponse.json();

                        if (pollData.status === 'completed' || pollData.status === 'error') {
                            return pollData;
                        }

                        overlay.innerHTML = `
                            <div class="text-center text-white">
                                <div class="spinner-border spinner-border-lg mb-2" role="status" style="width: 3rem; height: 3rem; border-width: 0.3em;">
                                    <span class="visually-hidden">Processando...</span>
                                </div>
                                <div class="fw-bold">${pollData.step || 'Processando IA...'}</div>
                                <small class="text-white-50">@${profile}</small>
                                ${pollData.progress !== undefined ? `<div class="text-white-50 mt-2" style="font-size: 0.75rem;">${pollData.progress}%</div>` : ''}
                            </div>
                        `;

                        await new Promise(resolve => setTimeout(resolve, 5000));
                    }

                    return {
                        success: false,
                        status: 'error',
                        message: 'Timeout: o processamento demorou mais que o esperado.'
                    };
                }

                const finalData = data.job_id ? await pollExtractProfileJob(data.job_id) : data;

                // Remover overlay quando finalizar
                overlay.remove();

                const isCompleted = finalData.status ? finalData.status === 'completed' : !!finalData.success;

                // Esconder o botão "Extrair" somente quando completar
                const extractButton = targetCard.querySelector('button[onclick*="extractProfileData"]');
                if (extractButton && isCompleted) {
                    extractButton.style.display = 'none';
                }

                // Criar mensagem apenas quando o processamento realmente finalizar
                const buttonsContainer = targetCard.querySelector('.d-flex.gap-2');
                if (buttonsContainer && isCompleted) {
                    // Verificar se já existe uma mensagem de sucesso
                    const existingMessage = targetCard.querySelector('.extraction-success-message');
                    if (existingMessage) {
                        existingMessage.remove();
                    }

                    const successMessage = document.createElement('div');
                    successMessage.className = (finalData.success ? 'alert alert-success' : 'alert alert-warning') + ' mt-2 mb-0 extraction-success-message';
                    successMessage.style.cssText = 'font-size: 0.875rem; padding: 0.5rem 0.75rem;';

                    const totalExtracted = finalData.total_extracted || 0;
                    const savedCount = finalData.saved_count || 0;
                    const skippedCount = finalData.skipped_count || 0;
                    const skippedItems = finalData.skipped_items || [];

                    const escapeHtml = (unsafe) => String(unsafe ?? '')
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#039;');

                    const skippedHtml = (skippedItems && skippedItems.length > 0)
                        ? skippedItems.map(i => {
                            const varName = i.variable ? `(${escapeHtml(i.variable)}) ` : '';
                            return `${varName}${escapeHtml(i.content)}`;
                        }).join('<br>')
                        : '';

                    const hasNew = savedCount > 0;
                    const headerText = hasNew ? 'Extração concluída!' : 'Extração concluída (sem novos itens)!';
                    const subTitleText = `${totalExtracted} item(ns) extraído(s) | ${savedCount} novo(s) adicionado(s) | ${skippedCount} já existentes`;

                    const alreadyExistsDetailsHtml = (skippedCount > 0 && skippedHtml)
                        ? `<small class="text-muted mt-1 d-block"><strong>Itens já existiam:</strong><br>${skippedHtml}</small>`
                        : '';

                    successMessage.innerHTML = `
                        <div class="d-flex align-items-center">
                            <svg xmlns="http://www.w3.org/2000/svg" class="icon me-2" width="18" height="18" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                <path d="M5 12l5 5l10 -10"/>
                            </svg>
                            <div class="flex-grow-1">
                                <strong>${headerText}</strong><br>
                                <small>${subTitleText}</small>
                                <br>
                                <small class="text-muted mt-1 d-block">
                                    Atualize a página para ver os itens adicionados
                                    <a href="javascript:void(0);" onclick="window.location.reload();" class="text-primary text-decoration-underline" style="cursor: pointer;">clicando aqui</a>
                                </small>
                                ${alreadyExistsDetailsHtml}
                            </div>
                        </div>
                    `;

                    // Inserir mensagem após o container de botões
                    buttonsContainer.parentElement.appendChild(successMessage);
                }

                if (finalData.success) {
                    toastr.success(finalData.message || 'Extração concluída com sucesso!');
                } else {
                    toastr.warning(finalData.message || 'Extração concluída com avisos.');
                }

            } catch (error) {
                console.error('Erro ao extrair perfil:', error);
                overlay.remove();
                toastr.error('Erro ao extrair dados do perfil. Tente novamente.');
            }
        }

        // ─── Viral Topics Modal ───────────────────────────────────────────────────

        window.vtAllProfiles = [];
        window.vtCurrentPage = 1;
        window.vtProfilesPerPage = 12;
        window.vtSearchTerm = '';
        window.vtSelectedNicheIds = [];
        window.vtSelectedProfessionIds = [];
        window.vtNicheSelect = null;
        window.vtProfessionSelect = null;

        async function openExtractViralTopicsModal() {
            const modalElement = document.getElementById('extractViralTopicsModal');
            if (!modalElement) {
                toastr.error('Erro: Modal não encontrado. Recarregue a página.');
                return;
            }

            const existingModal = bootstrap.Modal.getInstance(modalElement);
            if (existingModal) existingModal.dispose();

            const modal = new bootstrap.Modal(modalElement, { backdrop: true, keyboard: true, focus: true });
            modalElement.style.zIndex = '1055';
            modal.show();

            const loading = document.getElementById('vt-extract-loading');
            const content = document.getElementById('vt-extract-content');
            const empty = document.getElementById('vt-extract-empty');
            const container = document.getElementById('vt-profiles-container');

            loading.style.display = 'flex';
            content.style.display = 'none';
            empty.style.display = 'none';
            container.innerHTML = '';

            const searchInput = document.getElementById('vt-profile-search-input');
            if (searchInput) searchInput.value = '';
            window.vtSearchTerm = '';
            window.vtCurrentPage = 1;
            window.vtSelectedNicheIds = [];
            window.vtSelectedProfessionIds = [];

            setTimeout(async () => {
                initializeViralTopicsProfileFilters();

                try {
                    const userFiltersResponse = await fetch('/dashboard/user/profile/get-niches-professions', {
                        headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content') }
                    });
                    const userFiltersData = await userFiltersResponse.json();
                    if (userFiltersData.success && userFiltersData.data) {
                        setTimeout(() => {
                            const nicheIds = userFiltersData.data.niches || [];
                            const professionIds = userFiltersData.data.professions || [];
                            if (nicheIds.length > 0 && window.vtNicheSelect) {
                                window.vtNicheSelect.setValue(nicheIds, true);
                                window.vtSelectedNicheIds = nicheIds;
                            }
                            if (professionIds.length > 0 && window.vtProfessionSelect) {
                                window.vtProfessionSelect.setValue(professionIds, true);
                                window.vtSelectedProfessionIds = professionIds;
                            }
                            if ((nicheIds.length > 0 || professionIds.length > 0) && window.vtAllProfiles.length > 0) {
                                renderViralTopicsProfiles();
                            }
                        }, 500);
                    }
                } catch (e) {
                    console.warn('Erro ao buscar filtros do usuário:', e);
                }
            }, 100);

            try {
                const response = await fetch('/dashboard/user/searches/approved-profiles-viral-topics', {
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content') }
                });
                const data = await response.json();

                if (data.success && data.data && data.data.length > 0) {
                    window.vtAllProfiles = data.data;
                    window.vtCurrentPage = 1;
                    renderViralTopicsProfiles();
                    loading.style.display = 'none';
                    content.style.display = 'block';
                } else {
                    loading.style.display = 'none';
                    empty.style.display = 'block';
                }
            } catch (error) {
                console.error('Erro ao buscar perfis:', error);
                loading.style.display = 'none';
                empty.style.display = 'block';
                toastr.error('Erro ao carregar perfis. Tente novamente.');
            }
        }

        function initializeViralTopicsProfileFilters() {
            if (typeof TomSelect === 'undefined') {
                setTimeout(initializeViralTopicsProfileFilters, 100);
                return;
            }
            if (window.vtNicheSelect) window.vtNicheSelect.destroy();
            if (window.vtProfessionSelect) window.vtProfessionSelect.destroy();

            const nicheEl = document.getElementById('vt-profile-filter-niche');
            const professionEl = document.getElementById('vt-profile-filter-profession');
            if (!nicheEl || !professionEl) {
                setTimeout(initializeViralTopicsProfileFilters, 100);
                return;
            }

            window.vtNicheSelect = new TomSelect('#vt-profile-filter-niche', {
                copyClassesToDropdown: false,
                dropdownParent: 'body',
                create: false,
                placeholder: 'Selecione os nichos...',
                onChange: function(values) {
                    window.vtSelectedNicheIds = values || [];
                    window.vtCurrentPage = 1;
                    renderViralTopicsProfiles();
                }
            });
            window.vtProfessionSelect = new TomSelect('#vt-profile-filter-profession', {
                copyClassesToDropdown: false,
                dropdownParent: 'body',
                create: false,
                placeholder: 'Selecione as profissões...',
                onChange: function(values) {
                    window.vtSelectedProfessionIds = values || [];
                    window.vtCurrentPage = 1;
                    renderViralTopicsProfiles();
                }
            });
        }

        function filterViralTopicsProfiles() {
            const input = document.getElementById('vt-profile-search-input');
            window.vtSearchTerm = input ? input.value.toLowerCase() : '';
            window.vtCurrentPage = 1;
            renderViralTopicsProfiles();
        }

        function clearViralTopicsProfileSearch() {
            const input = document.getElementById('vt-profile-search-input');
            if (input) input.value = '';
            if (window.vtNicheSelect) window.vtNicheSelect.clear();
            if (window.vtProfessionSelect) window.vtProfessionSelect.clear();
            window.vtSearchTerm = '';
            window.vtSelectedNicheIds = [];
            window.vtSelectedProfessionIds = [];
            window.vtCurrentPage = 1;
            renderViralTopicsProfiles();
        }

        function renderViralTopicsProfiles() {
            const container = document.getElementById('vt-profiles-container');
            const paginationContainer = document.getElementById('vt-profiles-pagination');

            if (!container || !window.vtAllProfiles || window.vtAllProfiles.length === 0) {
                if (container) container.innerHTML = '';
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            let filtered = window.vtAllProfiles;

            if (window.vtSearchTerm) {
                filtered = filtered.filter(p => (p.profile || '').toLowerCase().includes(window.vtSearchTerm));
            }
            if (window.vtSelectedNicheIds && window.vtSelectedNicheIds.length > 0) {
                filtered = filtered.filter(p => p.niche_ids && p.niche_ids.length > 0 &&
                    window.vtSelectedNicheIds.some(id => p.niche_ids.includes(parseInt(id))));
            }
            if (window.vtSelectedProfessionIds && window.vtSelectedProfessionIds.length > 0) {
                filtered = filtered.filter(p => p.profession_ids && p.profession_ids.length > 0 &&
                    window.vtSelectedProfessionIds.some(id => p.profession_ids.includes(parseInt(id))));
            }

            if (filtered.length === 0) {
                container.innerHTML = `
                    <div class="col-12 text-center py-5">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-lg text-muted mb-3" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"/><path d="M21 21l-6 -6"/></svg>
                        <p class="text-muted">Nenhum perfil encontrado com os filtros aplicados.</p>
                    </div>`;
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            const totalPages = Math.ceil(filtered.length / window.vtProfilesPerPage);
            const start = (window.vtCurrentPage - 1) * window.vtProfilesPerPage;
            const paginated = filtered.slice(start, start + window.vtProfilesPerPage);

            container.innerHTML = '';

            paginated.forEach(profile => {
                const card = document.createElement('div');
                card.className = 'col-md-6 col-lg-4 mb-4';

                let thumbnailsHtml = '';
                if (profile.thumbnails && profile.thumbnails.length > 0) {
                    profile.thumbnails.forEach((thumb, i) => {
                        thumbnailsHtml += `<div class="thumbnail-item" style="flex:1;min-width:0;"><img src="${thumb}" alt="Thumbnail ${i+1}" class="img-fluid rounded" style="width:100%;height:120px;object-fit:cover;" onerror="this.src='/back/static/placeholder.jpg'"></div>`;
                    });
                }
                const missing = 3 - (profile.thumbnails ? profile.thumbnails.length : 0);
                for (let i = 0; i < missing; i++) {
                    thumbnailsHtml += `<div class="thumbnail-item" style="flex:1;min-width:0;background:#f3f4f6;border-radius:4px;display:flex;align-items:center;justify-content:center;"><svg xmlns="http://www.w3.org/2000/svg" class="icon text-muted" width="32" height="32" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/></svg></div>`;
                }

                const socialIcon = profile.social === 'instagram'
                    ? '<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 4m0 4a4 4 0 0 1 4 -4h8a4 4 0 0 1 4 4v8a4 4 0 0 1 -4 4h-8a4 4 0 0 1 -4 -4z"/><path d="M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"/><path d="M16.5 7.5l0 .01"/></svg>'
                    : '<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 2m0 4a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v4a4 4 0 0 1 -4 4h-4a4 4 0 0 1 -4 -4z"/></svg>';

                card.innerHTML = `
                    <div class="card h-100" style="transition:transform .2s,box-shadow .2s;position:relative;"
                         onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)'"
                         onmouseout="this.style.transform='';this.style.boxShadow=''">
                        <div class="card-body p-3">
                            <div class="d-flex align-items-center mb-3">
                                <div class="me-2">${socialIcon}</div>
                                <h5 class="card-title mb-0 flex-grow-1">@${profile.profile}</h5>
                            </div>
                            <div class="thumbnails-container mb-3" style="display:flex;gap:4px;height:120px;">${thumbnailsHtml}</div>
                            <div class="d-flex gap-2 mt-1">
                                <button type="button"
                                        onclick="extractViralTopicData('${profile.profile}', '${profile.social}', ${profile.eng_reversa_search_id})"
                                        title="Extrair assuntos virais deste perfil"
                                        style="flex:1;display:flex;align-items:center;justify-content:center;gap:5px;height:36px;border-radius:20px;font-size:0.78rem;font-weight:600;background:linear-gradient(135deg,#7c3aed,#9333ea);color:#fff;border:none;cursor:pointer;transition:opacity .2s;"
                                        onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg>
                                    Extrair Assuntos Virais
                                </button>
                            </div>
                        </div>
                    </div>`;

                container.appendChild(card);
            });

            if (totalPages > 1 && paginationContainer) {
                let html = '<nav><ul class="pagination mb-0">';
                if (window.vtCurrentPage > 1) {
                    html += `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="vtChangePage(${window.vtCurrentPage - 1})">&laquo;</a></li>`;
                }
                for (let i = 1; i <= totalPages; i++) {
                    html += `<li class="page-item ${i === window.vtCurrentPage ? 'active' : ''}"><a class="page-link" href="javascript:void(0);" onclick="vtChangePage(${i})">${i}</a></li>`;
                }
                if (window.vtCurrentPage < totalPages) {
                    html += `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="vtChangePage(${window.vtCurrentPage + 1})">&raquo;</a></li>`;
                }
                html += '</ul></nav>';
                paginationContainer.innerHTML = html;
                paginationContainer.style.removeProperty('display');
            } else if (paginationContainer) {
                paginationContainer.style.display = 'none';
            }
        }

        function vtChangePage(page) {
            window.vtCurrentPage = page;
            renderViralTopicsProfiles();
            const container = document.getElementById('vt-profiles-container');
            if (container) container.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        async function extractViralTopicData(profile, social, engReversaSearchId) {
            const profileCards = document.querySelectorAll('#vt-profiles-container .col-md-6.col-lg-4.mb-4');
            let targetCard = null;
            profileCards.forEach(card => {
                const title = card.querySelector('.card-title');
                if (title && title.textContent.includes(`@${profile}`)) {
                    targetCard = card.querySelector('.card');
                }
            });

            if (!targetCard) {
                toastr.error('Perfil não encontrado.');
                return;
            }

            const overlay = document.createElement('div');
            overlay.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;background-color:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10;border-radius:4px;';
            overlay.innerHTML = `
                <div class="text-center text-white">
                    <div class="spinner-border spinner-border-lg mb-2" role="status" style="width:3rem;height:3rem;border-width:0.3em;"></div>
                    <div class="fw-bold">Extraindo assuntos virais...</div>
                    <small class="text-white-50">@${profile}</small>
                </div>`;

            if (getComputedStyle(targetCard).position === 'static') targetCard.style.position = 'relative';
            targetCard.appendChild(overlay);

            try {
                const response = await fetch('/dashboard/user/searches/extract-profile', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({ type: 'topic_virais', eng_reversa_search_id: engReversaSearchId })
                });

                const data = await response.json();
                overlay.remove();

                if (data.success) {
                    const extractBtn = targetCard.querySelector('button[onclick*="extractViralTopicData"]');
                    if (extractBtn) extractBtn.style.display = 'none';

                    const buttonsContainer = targetCard.querySelector('.d-flex.gap-2');
                    if (buttonsContainer) {
                        const existing = targetCard.querySelector('.extraction-success-message');
                        if (existing) existing.remove();

                        const msg = document.createElement('div');
                        msg.className = 'alert alert-success mt-2 mb-0 extraction-success-message';
                        msg.style.cssText = 'font-size:0.875rem;padding:0.5rem 0.75rem;';
                        msg.innerHTML = `
                            <div class="d-flex align-items-center">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon me-2" width="18" height="18" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>
                                <div class="flex-grow-1">
                                    <strong>Extração concluída!</strong><br>
                                    <small>${data.total_extracted || 0} extraído(s) | ${data.saved_count || 0} novo(s) adicionado(s)</small><br>
                                    <small class="text-muted">Atualize a página para ver os assuntos adicionados — <a href="javascript:void(0);" onclick="window.location.reload();" class="text-primary text-decoration-underline">clique aqui</a></small>
                                </div>
                            </div>`;
                        buttonsContainer.parentElement.appendChild(msg);
                    }
                    toastr.success(data.message || 'Assuntos virais extraídos com sucesso!');
                } else {
                    toastr.warning(data.message || 'Extração concluída com avisos.');
                }
            } catch (error) {
                console.error('Erro ao extrair assuntos virais:', error);
                overlay.remove();
                toastr.error('Erro ao extrair assuntos virais. Tente novamente.');
            }
        }

        // Funções para seleção em massa e exclusão
        function toggleSelectAll(type, variableId, checked) {
            const checkboxes = document.querySelectorAll(`.item-checkbox-${type}-${variableId}`);
            checkboxes.forEach(checkbox => {
                checkbox.checked = checked;
            });
            updateDeleteButton(type, variableId);
        }

        function updateDeleteButton(type, variableId) {
            const checkboxes = document.querySelectorAll(`.item-checkbox-${type}-${variableId}`);
            const checkedBoxes = Array.from(checkboxes).filter(cb => cb.checked);
            const deleteButton = document.getElementById(`delete-selected-${type}-${variableId}`);
            const approveButton = document.getElementById(`approve-selected-${type}-${variableId}`);
            const countSpan = document.getElementById(`count-selected-${type}-${variableId}`);

            if (checkedBoxes.length > 0) {
                if (deleteButton) {
                    deleteButton.classList.remove('d-none');
                }
                // Mostrar botão de aprovar apenas para itens pendentes
                if (approveButton && type === 'pending') {
                    approveButton.classList.remove('d-none');
                    const approveCountSpan = document.getElementById(`approve-count-selected-pending-${variableId}`);
                    if (approveCountSpan) {
                        approveCountSpan.textContent = checkedBoxes.length;
                    }
                }
                if (countSpan) {
                    countSpan.textContent = checkedBoxes.length;
                }
            } else {
                if (deleteButton) {
                    deleteButton.classList.add('d-none');
                }
                if (approveButton) {
                    approveButton.classList.add('d-none');
                }
            }
        }

        async function approveSelectedItems(type, variableId) {
            if (type !== 'pending') {
                toastr.warning('Aprovação em massa só está disponível para itens pendentes.');
                return;
            }

            const checkboxes = document.querySelectorAll(`.item-checkbox-pending-${variableId}`);
            const selectedIds = Array.from(checkboxes)
                .filter(cb => cb.checked)
                .map(cb => parseInt(cb.value));

            if (selectedIds.length === 0) {
                toastr.warning('Nenhum item selecionado.');
                return;
            }

            try {
                // Aprovar cada item individualmente
                let successCount = 0;
                let errorCount = 0;

                for (const itemId of selectedIds) {
                    try {
                        const response = await fetch(`/dashboard/user/searches/approve-pending-item/${itemId}`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                                    'content')
                            }
                        });

                        const data = await response.json();

                        if (data.success) {
                            successCount++;
                            // Remover o item do DOM
                            const card = document.querySelector(`.card[data-item-id="${itemId}"]`);
                            if (card) {
                                const parentContainer = card.closest('.pending-item-container');
                                if (parentContainer) {
                                    parentContainer.style.transition = 'opacity 0.3s ease';
                                    parentContainer.style.opacity = '0';
                                    parentContainer.remove()
                                    // setTimeout(() => parentContainer.remove(), 300);
                                }
                            }
                        } else {
                            errorCount++;
                        }
                    } catch (error) {
                        console.error(`Erro ao aprovar item ${itemId}:`, error);
                        errorCount++;
                    }
                }

                // Atualizar contadores e botões
                updateDeleteButton('pending', variableId);
                updatePendingTabCounter(variableId);
                const selectAllCheckbox = document.getElementById(`select-all-pending-${variableId}`);
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = false;
                }

                // Mostrar resultado
                if (successCount > 0) {
                    toastr.success(`${successCount} item(ns) aprovado(s) com sucesso!`);
                }
                if (errorCount > 0) {
                    toastr.warning(`${errorCount} item(ns) não puderam ser aprovados.`);
                }

                // Verificar se não há mais itens
                const container = document.getElementById(`pending-items-${variableId}`);
                if (container) {
                    const remainingItems = container.querySelectorAll('.pending-item-container');
                    if (remainingItems.length === 0) {
                        container.innerHTML = `
                            <div class="text-muted text-center py-3">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon mb-2" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                    <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                                    <path d="M12 7l0 5l3 3" />
                                </svg>
                                <p>Nenhum item pendente</p>
                            </div>
                        `;
                    }
                }

                let activeTab = document.querySelector('.tab-pane.active[data-type]');
                if(activeTab) {
                    const type1 = activeTab.getAttribute('data-type');
                    if(type1) await loadTabVariables(type1);
                }

            } catch (error) {
                console.error('Erro ao aprovar itens:', error);
                toastr.error('Erro ao processar a solicitação.');
            }
        }

        async function deleteSelectedItems(type, variableId) {
            const checkboxes = document.querySelectorAll(`.item-checkbox-${type}-${variableId}`);
            // Coletar IDs com suas origens (source)
            const selectedItems = Array.from(checkboxes)
                .filter(cb => cb.checked)
                .map(cb => ({
                    id: parseInt(cb.value),
                    source: cb.getAttribute('data-source') || (type === 'pending' ? 'pending' : 'content')
                }));

            if (selectedItems.length === 0) {
                toastr.warning('Nenhum item selecionado.');
                return;
            }

            // Mostrar modal de confirmação
            const modalElement = document.getElementById('modal-confirm-bulk-delete');
            const messageEl = document.getElementById('bulk-delete-message');
            messageEl.textContent = `Você realmente deseja excluir ${selectedItems.length} item(ns) selecionado(s)?`;

            // Verificar se já existe uma instância do modal e removê-la
            const existingModal = bootstrap.Modal.getInstance(modalElement);
            if (existingModal) {
                existingModal.dispose();
            }

            // Configurar o botão de confirmação
            const confirmBtn = document.getElementById('confirm-bulk-delete-btn');
            confirmBtn.onclick = async function(e) {
                e.preventDefault();
                const modal = bootstrap.Modal.getInstance(modalElement);
                if (modal) {
                    modal.hide();
                }
                await performBulkDelete(type, variableId, selectedItems);
            };

            // Criar e mostrar o modal
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true
            });
            modal.show();
        }

        async function performBulkDelete(type, variableId, selectedItems) {
            // Separar IDs por origem (source)
            const itemsBySource = {
                content: [],
                pending: []
            };

            selectedItems.forEach(item => {
                if (item.source === 'content') {
                    itemsBySource.content.push(item.id);
                } else if (item.source === 'pending') {
                    itemsBySource.pending.push(item.id);
                }
            });

            try {
                const response = await fetch('/dashboard/user/searches/variables/contents/bulk-delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                            'content')
                    },
                    body: JSON.stringify({
                        items: selectedItems, // Enviar itens completos com source
                        items_by_source: itemsBySource, // Enviar também separado por origem
                        type: type,
                        variable_id: variableId
                    })
                });

                const data = await response.json();

                if (data.success) {
                    toastr.success(data.message);

                    // Remover os itens do DOM
                    selectedItems.forEach(item => {
                        // Buscar o card pelo data-item-id (agora está na div.card)
                        const card = document.querySelector(`.card[data-item-id="${item.id}"]`);
                        if (card) {
                            // Encontrar o container pai e remover ele (assim remove o card inteiro)
                            const parentContainer = card.closest('.pending-item-container');
                            if (parentContainer) {
                                parentContainer.style.transition = 'opacity 0.3s ease';
                                parentContainer.style.opacity = '0';
                                setTimeout(() => parentContainer.remove(), 300);
                            } else {
                                // Fallback: remover apenas o card se não encontrar o container
                                card.style.transition = 'opacity 0.3s ease';
                                card.style.opacity = '0';
                                setTimeout(() => card.remove(), 300);
                            }
                        }
                    });

                    // Atualizar contadores e botões
                    updateDeleteButton(type, variableId);
                    const selectAllCheckbox = document.getElementById(`select-all-${type}-${variableId}`);
                    if (selectAllCheckbox) {
                        selectAllCheckbox.checked = false;
                    }

                    // Verificar se não há mais itens
                    const container = document.getElementById(`${type}-items-${variableId}`);
                    if (container) {
                        const remainingItems = container.querySelectorAll('.pending-item-container');
                        if (remainingItems.length === 0) {
                            container.innerHTML = `
                                <div class="text-muted text-center py-3">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="icon mb-2" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                        <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                        <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                                        <path d="M12 7l0 5l3 3" />
                                    </svg>
                                    <p>Nenhum item ${type === 'approved' ? 'aprovado' : 'pendente'}</p>
                                </div>
                            `;
                        }
                    }

                    // NÃO recarregar dados - os itens já foram removidos visualmente do DOM
                    // Recarregar apenas se o usuário mudar de tab manualmente
                } else {
                    toastr.error(data.message);
                }
            } catch (error) {
                console.error('Erro ao excluir itens:', error);
                toastr.error('Erro ao processar a solicitação.');
            }
        }

        async function emptyVariable(variableId, type) {
            // Mostrar modal de confirmação
            const modalElement = document.getElementById('modal-confirm-empty-variable');
            const messageEl = document.getElementById('empty-variable-message');
            messageEl.textContent =
                `Você realmente deseja esvaziar TODOS os itens ${type === 'approved' ? 'aprovados' : 'pendentes'} desta variável? Esta ação não pode ser desfeita.`;

            // Verificar se já existe uma instância do modal e removê-la
            const existingModal = bootstrap.Modal.getInstance(modalElement);
            if (existingModal) {
                existingModal.dispose();
            }

            // Configurar o botão de confirmação
            const confirmBtn = document.getElementById('confirm-empty-variable-btn');
            confirmBtn.onclick = async function(e) {
                e.preventDefault();
                const modal = bootstrap.Modal.getInstance(modalElement);
                if (modal) {
                    modal.hide();
                }
                await performEmptyVariable(variableId, type);
            };

            // Criar e mostrar o modal
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true
            });
            modal.show();
        }

        async function performEmptyVariable(variableId, type) {
            try {
                const response = await fetch('/dashboard/user/searches/variables/contents/empty', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                            'content')
                    },
                    body: JSON.stringify({
                        variable_id: variableId,
                        type: type
                    })
                });

                const data = await response.json();

                if (data.success) {
                    toastr.success(data.message);

                    // Limpar o container
                    const container = document.getElementById(`${type}-items-${variableId}`);
                    if (container) {
                        container.innerHTML = `
                            <div class="text-muted text-center py-3">
                                <svg xmlns="http://www.w3.org/2000/svg" class="icon mb-2" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                    <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                                    <path d="M12 7l0 5l3 3" />
                                </svg>
                                <p>Nenhum item ${type === 'approved' ? 'aprovado' : 'pendente'}</p>
                            </div>
                        `;
                    }

                    // Atualizar botões
                    updateDeleteButton(type, variableId);
                    const selectAllCheckbox = document.getElementById(`select-all-${type}-${variableId}`);
                    if (selectAllCheckbox) {
                        selectAllCheckbox.checked = false;
                    }

                    // NÃO recarregar dados - os itens já foram removidos visualmente do DOM
                    // Recarregar apenas se o usuário mudar de tab manualmente
                } else {
                    toastr.error(data.message);
                }
            } catch (error) {
                console.error('Erro ao esvaziar variável:', error);
                toastr.error('Erro ao processar a solicitação.');
            }
        }

        // Função para obter parâmetros da URL
        function getUrlParameter(name) {
            const urlParams = new URLSearchParams(window.location.search);
            return urlParams.get(name);
        }

        // Event delegation global para botões de remover
        document.body.addEventListener('click', function(e) {
            // Verifica se o clique foi em um botão de remover ou dentro dele
            let btn = null;
            if (e.target.classList.contains('remove-item-btn')) {
                btn = e.target;
            } else if (e.target.closest('.remove-item-btn')) {
                btn = e.target.closest('.remove-item-btn');
            }

            if (btn) {
                e.preventDefault();
                e.stopPropagation();

                const variableId = btn.getAttribute('data-variable-id');
                const itemId = btn.getAttribute('data-item-id');

                // Buscar a origem (source) - primeiro do botão, depois do card pai
                let source = btn.getAttribute('data-source');
                if (!source) {
                    const card = btn.closest('.card');
                    source = card ? (card.getAttribute('data-source') || 'content') : 'content';
                }

                if (variableId && itemId) {
                    const funcName = 'openRemoveModal' + variableId;
                    const openModalFunc = window[funcName];

                    if (typeof openModalFunc === 'function') {
                        openModalFunc(itemId, source);
                    } else {
                        console.error('Função não encontrada:', funcName);
                    }
                }
            }
        });

        // Inicialização das tabs na página
        (function initializeTabs() {
            // Verifica se há um parâmetro 'tab' na URL
            const tabParam = getUrlParameter('tab');
            let activeTab = null;

            if (tabParam) {
                // Se há parâmetro na URL, tenta encontrar o tab correspondente pelo ID
                // O parâmetro é o ID do tab: 'me', 'public', etc.
                activeTab = document.getElementById(tabParam);

                if (activeTab && activeTab.hasAttribute('data-type')) {
                    // Ativa o tab correto
                    document.querySelectorAll('.tab-pane').forEach(tab => {
                        tab.classList.remove('show', 'active');
                    });
                    activeTab.classList.add('show', 'active');

                    // Também ativa o link da tab correspondente
                    document.querySelectorAll('[data-tab]').forEach(link => {
                        const tabName = link.getAttribute('data-tab');
                        if (tabName === tabParam) {
                            // Remove active de todos os links
                            document.querySelectorAll('[data-tab]').forEach(l => {
                                l.classList.remove('active');
                            });
                            // Adiciona active ao link correto
                            link.classList.add('active');
                        }
                    });
                } else {
                    // Se o tab não foi encontrado, usa o padrão
                    activeTab = null;
                }
            }

            // Se não encontrou tab por parâmetro, usa o tab ativo padrão
            if (!activeTab) {
                activeTab = document.querySelector('.tab-pane.active[data-type]');
            }

            // Carrega os dados do tab ativo
            if (activeTab && activeTab.hasAttribute('data-type')) {
                const type = activeTab.getAttribute('data-type');
                loadTabVariables(type);
                activeTab.setAttribute('data-loaded', 'true');
            }

            // Adiciona listeners para os cliques nas tabs
            document.querySelectorAll('[data-tab]').forEach(link => {
                link.addEventListener('click', function() {
                    const tabName = this.getAttribute('data-tab');
                    const tab = document.getElementById(tabName);

                    if (tab && tab.hasAttribute('data-type') && tab.getAttribute('data-loaded') ===
                        'false') {
                        const type = tab.getAttribute('data-type');
                        tab.setAttribute('data-loaded', 'true');

                        if (type === 'unified') {
                            setTimeout(() => {
                                if (typeof loadUnifiedData === 'function') loadUnifiedData();
                            }, 0);
                        } else {
                            const loading = document.getElementById('global-variables-loading');
                            const content = document.getElementById('variables-content');

                            if (loading) loading.style.display = 'flex';
                            if (content) content.style.display = 'none';

                            setTimeout(() => loadTabVariables(type), 100);
                        }
                    }
                });
            });
        })();
    