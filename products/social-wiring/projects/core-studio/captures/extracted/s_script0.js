
    function deleteItemViral(id, parentElement = false) {
        // Encontrar por data-item-id específico
        var div = $('.card.border-warning.bg-warning-lt[data-item-id="' + id + '"]');

        // Ou de forma mais simples (busca qualquer elemento com data-item-id)
        var div = $('[data-item-id="' + id + '"]');

        // Se você tem o ID em uma variável
        var itemId = id;
        var div = $('[data-item-id="' + itemId + '"]');

        // Ou usando template literals (ES6)
        var div = $(`[data-item-id="${itemId}"]`);

        if (!div.length) {
            console.warn('Item viral não encontrado:', id);
            return;
        }

        if (parentElement) {
            div = div.parent();
            div.remove();
            return;
        }

        div.addClass('d-none');
    }
    // Declarar handleViralAction no escopo global ANTES do // para garantir que esteja disponível quando o HTML for renderizado
    window.handleViralAction = async function(type, id) {
        try {
            const url = `dashboard/user/searches/viral/topics/${type}/${id}`;
            const response = await fetch(url);
            const data = await response.json();

            if (data.success) {
                toastr.success(data.message);

                // Usar a função que já está funcionando para remover o item
                deleteItemViral(id, true);
                addNewApproveViralTopic(data?.viral_topic)
                updateViralPendingCounter();
                // location.reload();
            } else {
                toastr.error(data.message);
            }
        } catch (error) {
            toastr.error('Erro ao processar a solicitação.');
            console.error(error);
        }
    };

    function formatNumberWithSuffix(numb, allowConvertNumberView = false) {
        if (!numb) {
            return '0';
        }

        // Remove pontos (se vier tipo "1.234.567")
        const number = parseInt(String(numb).replace(/\./g, ''), 10);

        if (!allowConvertNumberView) {
            return number.toLocaleString('pt-BR');
        }

        if (number < 1000) {
            return String(number);
        }

        let divisor = 1;
        let suffix = '';

        if (number < 1_000_000) {
            divisor = 1000;
            suffix = 'K';
        } else {
            divisor = 1_000_000;
            suffix = 'M';
        }

        let result = (number / divisor).toFixed(1);

        // Remove .0
        result = result.replace(/\.0$/, '');

        return result + suffix;
    }

    function addNewApproveViralTopic(sv) {
        if (!sv) {
            return '';
        }

        const containerApproveItems = document.querySelector('#viral-topics-badges');
        if(containerApproveItems) {

            const element = document.createElement('span');
            element.classList.add('viral-topic-badge', 'd-none', 'flex-grow-1', 'text-center', 'badge-topic');
            element.title = 'Clique para ver os virais';
            element.style.cursor = 'pointer';
            element.style.position = 'relative';
            element.style.paddingLeft = '2.5rem';
            element.setAttribute('onclick', `openViralModal(${sv?.id}, '${ sv?.topic }')`);
            element.innerHTML = `
                <div class="form-check"
                    style="position: absolute; left: 8px; top: 50%; transform: translateY(-50%); z-index: 10;"
                    onclick="event.stopPropagation();">
                    <input class="form-check-input item-checkbox-approved-viral"
                        type="checkbox" value="${ sv.id }"
                        id="checkbox-approved-viral-${ sv.id }"
                        onchange="updateDeleteButtonViral('approved')"
                        style="background-color: rgba(255,255,255,0.3); border-color: rgba(255,255,255,0.5);"
                        onclick="event.stopPropagation();">
                </div>
                ${ sv.topic }
                ${sv.total_plays ?? 0 > 0 ?  `<span class="viral-topic-views"> ${formatNumberWithSuffix(sv.total_plays, true)} Views </span>` : ''}
                <button type="button"
                    class="btn-close btn-close-white ms-auto viral-topic-remove-btn"
                    aria-label="Remover" style="font-size: 0.7em;" data-bs-toggle="modal"
                    data-bs-target="#modal-remove-topic" data-id="${ sv.id }"
                    onclick="event.stopPropagation(); openRemoveModal(${ sv.id });"></button>
            `;

            containerApproveItems.appendChild(element)

            showViralTopics();
        }

    }
