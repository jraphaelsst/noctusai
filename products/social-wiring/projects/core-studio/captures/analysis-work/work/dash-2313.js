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
    
