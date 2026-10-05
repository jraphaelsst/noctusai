
        document.addEventListener('DOMContentLoaded', function () {
            let modal = document.getElementById('modal-yt-video');
            let iframe = modal.querySelector('iframe');

            modal.addEventListener('hidden.bs.modal', function () {
                iframe.src = "";
            });
        });

        function openVideo(url) {
            let modal = new bootstrap.Modal(document.getElementById('modal-yt-video'));
            let iframe = document.querySelector('#modal-yt-video iframe');
            iframe.src = url;  // Define o link do vídeo quando abrir o modal
            modal.show();
        }
        
    