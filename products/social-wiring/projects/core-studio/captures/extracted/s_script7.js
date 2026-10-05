
    // Carrega Tópicos por quantidade
    document.addEventListener("DOMContentLoaded", () => {
       showViralTopics()
    });

    function showViralTopics() {
        const badges = Array.from(document.querySelectorAll("#viral-topics-badges span"));
        const loadMoreBtn = document.getElementById("loadMoreBtn");
        const itemsPerClick = 27;
        let currentIndex = 0;

        function showMore() {
            const nextItems = badges.slice(currentIndex, currentIndex + itemsPerClick);
            nextItems.forEach(b => b.classList.remove("d-none"));
            currentIndex += itemsPerClick;

            if (currentIndex >= badges.length) loadMoreBtn.style.display = "none";
        }

        showMore();

        loadMoreBtn.addEventListener("click", showMore);
    }

    // Add Tópico
    const newViralTopicInput = document.getElementById("new-viral-topic");
    if (newViralTopicInput) {
        newViralTopicInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addViralTopic();
            }
        });
    }

    function addViralTopic() {
        const input = $("#new-viral-topic");
        const btn = $("#add-viral-btn");
        const originalText = btn.text();
        const topicValue = input.val().trim();

        if (!topicValue) {
            toastr.error('Digite um tópico válido!');
            return;
        }

        btn.prop('disabled', true);
        btn.text('Salvando...');

        $.ajax({
            url: 'dashboard/user/searches/viral/topics/add',
            method: 'POST',
            headers: {
                'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
            },
            data: {
                topic: topicValue
            },
            success: function(data) {
                if (data.success) {
                    toastr.success(data.message);
                    input.val('');

                    // Adiciona o novo tópico à lista de aprovados via AJAX usando dados do backend
                    if (data.viral_topic && typeof addViralToApprovedList === 'function') {
                        addViralToApprovedList(data.viral_topic);
                    }
                } else {
                    toastr.error(data.message);
                }
            },
            error: function(err) {
                toastr.error('Erro ao processar a solicitação.');
            },
            complete: function() {
                btn.prop('disabled', false);
                btn.text(originalText);
            }
        });
    }

    // Funções para seleção em massa de assuntos virais
    function toggleSelectAllViral(type, checked) {
        const checkboxes = document.querySelectorAll(`.item-checkbox-${type}-viral`);
        checkboxes.forEach(checkbox => {
            checkbox.checked = checked;
        });
        updateDeleteButtonViral(type);
    }

    function updateDeleteButtonViral(type) {
        const checkboxes = document.querySelectorAll(`.item-checkbox-${type}-viral`);
        const checkedBoxes = Array.from(checkboxes).filter(cb => cb.checked);
        const deleteButton = document.getElementById(`delete-selected-${type}-viral`);
        const approveButton = document.getElementById(`approve-selected-${type}-viral`);
        const countSpan = document.getElementById(`count-selected-${type}-viral`);

        if (checkedBoxes.length > 0) {
            if (deleteButton) {
                deleteButton.classList.remove('d-none');
            }
            // Mostrar botão de aprovar apenas para itens pendentes
            if (approveButton && type === 'pending') {
                approveButton.classList.remove('d-none');
                const approveCountSpan = document.getElementById('approve-count-selected-pending-viral');
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

    async function approveSelectedViralTopics(type) {
        if (type !== 'pending') {
            toastr.warning('Aprovação em massa só está disponível para itens pendentes.');
            return;
        }

        const checkboxes = document.querySelectorAll('.item-checkbox-pending-viral');
        const selectedIds = Array.from(checkboxes)
            .filter(cb => cb.checked)
            .map(cb => parseInt(cb.value));

        if (selectedIds.length === 0) {
            toastr.warning('Nenhum item selecionado.');
            return;
        }

        try {
            // Aprovar cada item individualmente usando handleViralAction
            let successCount = 0;
            let errorCount = 0;

            for (const itemId of selectedIds) {
                try {
                    const url = `dashboard/user/searches/viral/topics/approve/${itemId}`;
                    const response = await fetch(url);
                    const data = await response.json();

                    if (data.success) {
                        successCount++;
                        // Remover o item do DOM usando a função que já existe
                        deleteItemViral(itemId, true);
                        addNewApproveViralTopic(data?.viral_topic);
                    } else {
                        errorCount++;
                    }
                } catch (error) {
                    console.error(`Erro ao aprovar item ${itemId}:`, error);
                    errorCount++;
                }
            }

            // Atualizar contadores e botões
            updateDeleteButtonViral('pending');
            updateViralPendingCounter();
            const selectAllCheckbox = document.getElementById('select-all-pending-viral');
            if (selectAllCheckbox) {
                selectAllCheckbox.checked = false;
            }

            // Mostrar resultado
            if (successCount > 0) {
                toastr.success(`${successCount} assunto(s) viral(is) aprovado(s) com sucesso!`);
            }
            if (errorCount > 0) {
                toastr.warning(`${errorCount} assunto(s) viral(is) não puderam ser aprovados.`);
            }

            // Verificar se não há mais itens
            const container = document.getElementById('pending-items');
            if (container) {
                const remainingItems = container.querySelectorAll('.pending-item-container');
                const visibleItems = Array.from(remainingItems).filter(item => {
                    const style = window.getComputedStyle(item);
                    return style.display !== 'none' && style.visibility !== 'hidden' && item
                        .offsetParent !== null;
                });

                if (visibleItems.length === 0) {
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

        } catch (error) {
            console.error('Erro ao aprovar assuntos virais:', error);
            toastr.error('Erro ao processar a solicitação.');
        }
    }

    async function deleteSelectedViralTopics(type) {
        console.log('[deleteSelectedViralTopics] Função chamada com type:', type);

        const checkboxes = document.querySelectorAll(`.item-checkbox-${type}-viral`);
        const selectedIds = Array.from(checkboxes)
            .filter(cb => cb.checked)
            .map(cb => parseInt(cb.value));

        console.log('[deleteSelectedViralTopics] IDs selecionados:', selectedIds);

        if (selectedIds.length === 0) {
            toastr.warning('Nenhum item selecionado.');
            return;
        }

        // Mostrar modal de confirmação
        console.log('[deleteSelectedViralTopics] Buscando modal...');
        const modalElement = document.getElementById('modal-confirm-bulk-delete-viral');
        console.log('[deleteSelectedViralTopics] Modal encontrado:', modalElement);
        if (!modalElement) {
            console.error('Modal modal-confirm-bulk-delete-viral não encontrado!');
            toastr.error('Erro: Modal não encontrado. Recarregue a página.');
            return;
        }

        const messageEl = document.getElementById('bulk-delete-viral-message');
        if (!messageEl) {
            console.error('Elemento bulk-delete-viral-message não encontrado!');
            toastr.error('Erro: Elemento não encontrado. Recarregue a página.');
            return;
        }
        messageEl.textContent =
            `Você realmente deseja excluir ${selectedIds.length} assunto(s) viral(is) selecionado(s)?`;

        // Verificar se já existe uma instância do modal e removê-la
        const existingModal = bootstrap.Modal.getInstance(modalElement);
        if (existingModal) {
            existingModal.dispose();
        }

        // Configurar o botão de confirmação
        const confirmBtn = document.getElementById('confirm-bulk-delete-viral-btn');
        if (!confirmBtn) {
            console.error('Botão confirm-bulk-delete-viral-btn não encontrado!');
            toastr.error('Erro: Botão não encontrado. Recarregue a página.');
            return;
        }

        confirmBtn.onclick = async function(e) {
            e.preventDefault();
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                modal.hide();
            }
            await performBulkDeleteViral(type, selectedIds);
        };

        // Criar e mostrar o modal
        try {
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true
            });
            modal.show();
            console.log('Modal de exclusão em massa de assuntos virais aberto com sucesso');
        } catch (error) {
            console.error('Erro ao abrir modal:', error);
            toastr.error('Erro ao abrir modal de confirmação.');
        }
    }

    async function performBulkDeleteViral(type, selectedIds) {
        try {
            const response = await fetch('/dashboard/user/searches/viral/topics/bulk-delete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                        'content')
                },
                body: JSON.stringify({
                    ids: selectedIds,
                    type: type
                })
            });

            const data = await response.json();

            if (data.success) {
                toastr.success(data.message);

                // Remover os itens do DOM
                selectedIds.forEach(id => {
                    if (type === 'approved') {
                        const checkbox = document.querySelector(`#checkbox-approved-viral-${id}`);
                        if (checkbox) {
                            const badge = checkbox.closest('span.badge-topic');
                            if (badge) {
                                badge.style.transition = 'opacity 0.3s ease';
                                badge.style.opacity = '0';
                                badge.remove()
                                // setTimeout(() => badge.remove(), 300);
                            }
                        }
                    } else {
                        // Buscar o card pelo data-item-id (agora está na div.card)
                        const card = document.querySelector(
                            `.card.border-warning.bg-warning-lt[data-item-id="${id}"]`);
                        if (card) {
                            // Encontrar o container pai e remover ele (assim remove o card inteiro)
                            const parentContainer = card.closest('.pending-item-container');
                            if (parentContainer) {
                                parentContainer.style.transition = 'opacity 0.3s ease';
                                parentContainer.style.opacity = '0';
                                parentContainer.remove()
                                // setTimeout(() => parentContainer.remove(), 300);
                            } else {
                                // Fallback: remover apenas o card se não encontrar o container
                                card.style.transition = 'opacity 0.3s ease';
                                card.style.opacity = '0';
                                card.remove()
                                // setTimeout(() => card.remove(), 300);
                            }
                        }
                    }
                });

                // Atualizar contadores e botões
                updateDeleteButtonViral(type);
                const selectAllCheckbox = document.getElementById(`select-all-${type}-viral`);
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = false;
                }

                // Verificar se não há mais itens
                if (type === 'pending') {
                    const container = document.getElementById('pending-items');
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
                }

                // Recarregar página após um delay
                // setTimeout(() => {
                //     window.location.reload();
                // }, 500);
            } else {
                toastr.error(data.message);
            }
        } catch (error) {
            console.error('Erro ao excluir assuntos virais:', error);
            toastr.error('Erro ao processar a solicitação.');
        }
    }

    async function emptyViralTopics(type) {
        // Mostrar modal de confirmação
        const modalElement = document.getElementById('modal-confirm-empty-viral');
        if (!modalElement) {
            console.error('Modal modal-confirm-empty-viral não encontrado!');
            toastr.error('Erro: Modal não encontrado. Recarregue a página.');
            return;
        }

        const messageEl = document.getElementById('empty-viral-message');
        if (!messageEl) {
            console.error('Elemento empty-viral-message não encontrado!');
            toastr.error('Erro: Elemento não encontrado. Recarregue a página.');
            return;
        }
        messageEl.textContent =
            `Você realmente deseja esvaziar TODOS os assuntos virais ${type === 'approved' ? 'aprovados' : 'pendentes'}? Esta ação não pode ser desfeita.`;

        // Verificar se já existe uma instância do modal e removê-la
        const existingModal = bootstrap.Modal.getInstance(modalElement);
        if (existingModal) {
            existingModal.dispose();
        }

        // Configurar o botão de confirmação
        const confirmBtn = document.getElementById('confirm-empty-viral-btn');
        if (!confirmBtn) {
            console.error('Botão confirm-empty-viral-btn não encontrado!');
            toastr.error('Erro: Botão não encontrado. Recarregue a página.');
            return;
        }

        confirmBtn.onclick = async function(e) {
            e.preventDefault();
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                modal.hide();
            }
            await performEmptyViralTopics(type);
        };

        // Criar e mostrar o modal
        try {
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true
            });
            modal.show();
            console.log('Modal de esvaziar assuntos virais aberto com sucesso');
        } catch (error) {
            console.error('Erro ao abrir modal:', error);
            toastr.error('Erro ao abrir modal de confirmação.');
        }
    }

    async function performEmptyViralTopics(type) {
        try {
            const response = await fetch('/dashboard/user/searches/viral/topics/empty', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                        'content')
                },
                body: JSON.stringify({
                    type: type
                })
            });

            const data = await response.json();

            if (data.success) {
                toastr.success(data.message);

                // Recarregar página
                setTimeout(() => {
                    window.location.reload();
                }, 500);
            } else {
                toastr.error(data.message);
            }
        } catch (error) {
            console.error('Erro ao esvaziar assuntos virais:', error);
            toastr.error('Erro ao processar a solicitação.');
        }
    }
