/* ===== SCRIPT #12 @651673 attrs= len=2991 */

        const customRange = document.querySelector('#customRange');
        customRange.addEventListener('change', (e) => {
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

            document.getElementById(activeLabel).classList.add('active');

            currentElement.style.background =
                `linear-gradient(to right, #9945FF ${currentElement.value}%, #4C1F83 ${currentElement.value}%)`;

        });

        const headlineTypes = document.querySelectorAll('.radioGenerationType');
        headlineTypes.forEach(headlineType => {
            headlineType.addEventListener('click', () => {
                if (headlineType.querySelector('input').disabled) return;

                headlineTypes.forEach(headlineType => {
                    headlineType.classList.remove('active');
                });

                headlineType.classList.add('active');
            });
        });


        document.querySelector('#openAdvancedOptionsModal').addEventListener('click', function() {
            this.innerHTML = this.innerText === 'Opções Avançadas' ?
                `
                Esconder Opções Avançadas
                <svg style="width: 18px; margin-left: 5px" xmlns="http://www.w3.org/2000/svg" width="24" height="24"
                    viewBox="0 0 24 24" fill="none"  stroke="currentColor" stroke-width="2" stroke-linecap="round"
                    stroke-linejoin="round" class="lucide lucide-chevron-up-icon lucide-chevron-up">
                    <path d="m18 15-6-6-6 6"/>
                </svg>
            ` :
                `
                Opções Avançadas
                 <svg style="width: 18px; margin-left: 5px" xmlns="http://www.w3.org/2000/svg" width="24"
                    height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                    class="lucide lucide-chevron-down-icon lucide-chevron-down">
                    <path d="m6 9 6 6 6-6" />
                </svg>
            `;
            document.getElementById('advancedOptionsV2ID').classList.toggle('show');
        })

        document.querySelector('#clearFieldsV2').addEventListener('click', function() {
            selects.forEach(element => {
                document.getElementById(element).value = [];
                document.getElementById(element).tomselect.clear();
            });
        });
    
