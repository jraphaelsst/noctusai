
        async function addVariableToDb() {
            try {
                const url = `dashboard/user/searches/variables/contents/add`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({
                        id: document.getElementById('modalVariableId').value,
                        value: document.getElementById('variableValue').value
                    })
                });
                const data = await response.json();

                if (data.type === 'success') {
                    toastr.success(data.message);

                    // Obter o ID da variável
                    const variableId = document.getElementById('modalVariableId').value;

                    // Adicionar o novo item à lista de aprovados
                    const container = document.getElementById(`approved-items-${variableId}`);
                    if (container) {
                        // Remover mensagem de "Nenhum item aprovado" se existir
                        const emptyMessage = container.querySelector('.text-muted.text-center');
                        if (emptyMessage) {
                            emptyMessage.remove();
                        }

                        // Criar o HTML do novo item
                        const newItemHtml = renderApprovedManualItem(variableId, {
                            id: data.data.id,
                            content: data.data.content
                        });

                        // Adicionar o novo item ao início do container
                        container.insertAdjacentHTML('afterbegin', newItemHtml);
                    }

                    // Limpar o campo de valor após sucesso
                    document.getElementById('variableValue').value = '';
                } else {
                    toastr.error(data.message || 'Erro ao adicionar conteúdo');
                }
            } catch (error) {
                toastr.error('Erro ao processar a solicitação.');
                console.error(error);
            }
        }

    