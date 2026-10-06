$(document).ready(function () {

    const engagement = [profileInsights.accounts_engaged_month, profileInsights.accounts_engaged_week, profileInsights.accounts_engaged_day];
    const reach = [profileInsights.reach_month, profileInsights.reach_week, profileInsights.reach_day];
    const renderProfileData = () => {

        var engagementOptions = {
            chart: {
                type: 'area',
                height: 250,
                toolbar: { show: false },
                fontFamily: 'Inter, sans-serif'
            },
            series: [{
                name: 'Engajamento (%)',
                data: engagement
            }],
            xaxis: {
                categories: ['30 dias', '7 dias', 'Hoje'],
                labels: { style: { colors: '#f0f0ff' } },
                axisBorder: { color: '#1f2e41' },
                axisTicks: { color: '#1f2e41' }
            },
            yaxis: {
                labels: { style: { colors: '#f0f0ff' } }
            },
            colors: ['#0054A6'],
            fill: {
                type: 'gradient',
                gradient: {
                    shadeIntensity: 1,
                    opacityFrom: 0.2,
                    opacityTo: 0.2,
                    stops: [0, 100]
                }
            },
            dataLabels: { enabled: false },
            stroke: { curve: 'smooth', width: 2 },
            grid: { borderColor: '#1f2e41' },
            legend: {
                position: 'top',
                labels: { colors: '#f0f0ff' }
            },
            tooltip: {
                theme: 'dark',
                style: { fontSize: '12px', color: '#f0f0ff' },
                marker: { show: true },
                cssClass: 'apexcharts-tooltip-custom',
                custom: function ({ series, seriesIndex, dataPointIndex, w }) {
                    return '<div style=" color: #f0f0ff; padding: 8px; border-radius: 4px;">' +
                        '<span>' + w.globals.seriesNames[seriesIndex] + ': ' + series[seriesIndex][dataPointIndex] + '</span>' +
                        '</div>';
                }
            }
        };
        var engagementChart = new ApexCharts(document.querySelector("#chart-activities"), engagementOptions);
        engagementChart.render();

        // Reach Chart
        var reachOptions = {
            chart: {
                type: 'area',
                height: 250,
                toolbar: { show: false },
                fontFamily: 'Inter, sans-serif'
            },
            series: [{
                name: 'Alcance (K)',
                data: reach
            }],
            xaxis: {
                categories: ['30 dias', '7 dias', 'Hoje'],
                labels: { style: { colors: '#f0f0ff' } },
                axisBorder: { color: '#1f2e41' },
                axisTicks: { color: '#1f2e41' }
            },
            yaxis: {
                labels: { style: { colors: '#f0f0ff' } }
            },
            colors: ['#0054A6'],
            fill: {
                type: 'gradient',
                gradient: {
                    shadeIntensity: 1,
                    opacityFrom: 0.2,
                    opacityTo: 0.2,
                    stops: [0, 100]
                }
            },
            dataLabels: { enabled: false },
            stroke: { curve: 'smooth', width: 2 },
            grid: { borderColor: '#1f2e41' },
            legend: {
                position: 'top',
                labels: { colors: '#f0f0ff' }
            },
            tooltip: {
                theme: 'dark',
                style: { fontSize: '12px', color: '#f0f0ff' },
                marker: { show: true },
                cssClass: 'apexcharts-tooltip-custom',
                custom: function ({ series, seriesIndex, dataPointIndex, w }) {
                    return '<div style=" color: #f0f0ff; padding: 8px; border-radius: 4px;">' +
                        '<span>' + w.globals.seriesNames[seriesIndex] + ': ' + series[seriesIndex][dataPointIndex] + '</span>' +
                        '</div>';
                }
            }
        };
        var reachChart = new ApexCharts(document.querySelector("#chart-reach"), reachOptions);
        reachChart.render();
    }
    renderProfileData()


    function renderPosts() {

        const instagramMediaContainer = $("#instagram-media-container");
        instagramMediaContainer.empty();
        if (instagramPosts.data && instagramPosts.data.length > 0) {
            instagramMediaContainer.empty();
            instagramPosts.data.forEach(post => {
                var a = $("<a>")
                    .attr('href', post.permalink)
                    .attr('target', '_blank')
                    .addClass("col-12 col-md-6 col-xl-4")
                    .css({
                        'cursor': 'pointer',
                        'display': 'block'
                    })
                    .html(`
                            <div class="card">
                                <div class="card-body p-3">
                                    <div 
                                        class="d-flex align-items-center gap-3 mb-3">
                                        <img src="${post.media_type === 'VIDEO' ? post.thumbnail_url : post.media_url}"
                                            alt="Campaign Post"
                                            class="rounded border border-dark-custom"
                                            style="width: 80px; min-width: 80px; height: 80px; object-fit: cover;" />
                                        <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                            width: 100%; border-radius: 5px; padding: 8px 15px; display: flex; 
                                            flex-direction: column; justify-content: center">
                                            <p class="card-title m-0 p-0" style="font-size: 1.1rem;">
                                                ${post.media_type === 'VIDEO' ? 'Reels' : "Post"}</p>
                                            <p class="small m-0 p-0" style="color: #FFFFFF80 !important;">
                                                ${formatData(post.timestamp)}
                                            </p>
                                        </div>
                                    </div>
                                    <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                        border-radius: 5px"
                                        class="d-flex align-items-center p-2 bg-darker-custom mb-2">
                                        <svg width="16" height="16"
                                            viewBox="0 0 24 24" fill="none"
                                            stroke="#9945FF" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round"
                                            aria-hidden="true">
                                            <path
                                                d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z">
                                            </path>
                                        </svg>
                                        <span class="ms-2" style="">${convertLikes(post.likes)} Curtidas</span> 
                                    </div>
                                    <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                        border-radius: 5px"
                                        class="d-flex align-items-center p-2 bg-darker-custom mb-2">
                                        <svg width="16" height="16"
                                            viewBox="0 0 24 24" fill="none"
                                            stroke="#9945FF" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round"
                                            aria-hidden="true">
                                            <path
                                                d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z">
                                            </path>
                                        </svg>
                                        <span class="ms-2" style="">${convertLikes(post.comments)} Comentários</span>
                                    </div>
                                    <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                        border-radius: 5px"
                                        class="d-flex align-items-center p-2 bg-darker-custom mb-2">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9945FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <path d="M7 7l5-5 5 5"></path>
                                            <path d="M12 2v10"></path>
                                            <path d="M5 12l-2 5 2 5h14l2-5-2-5z"></path>
                                        </svg>
                                        <span class="ms-2" style="">${convertLikes(post.shares)} Compartilhamentos</span>
                                    </div>
                                    <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                        border-radius: 5px"
                                        class="d-flex align-items-center p-2 bg-darker-custom mb-2">
                                        <svg width="16" height="16"
                                            viewBox="0 0 24 24" fill="none"
                                            stroke="#9945FF" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round"
                                            aria-hidden="true">
                                            <circle cx="12" cy="12" r="10">
                                            </circle>
                                            <circle cx="12" cy="12" r="4">
                                            </circle>
                                            <line x1="4.93" y1="4.93"
                                                x2="9.17" y2="9.17"></line>
                                            <line x1="14.83" y1="14.83"
                                                x2="19.07" y2="19.07"></line>
                                            <line x1="14.83" y1="9.17"
                                                x2="19.07" y2="4.93"></line>
                                            <line x1="4.93" y1="19.07"
                                                x2="9.17" y2="14.83"></line>
                                        </svg>
                                        <span class="ms-2" style="">${convertLikes(post.views)} Visualizações</span>
                                    </div>
                                    <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                        border-radius: 5px"
                                        class="d-flex align-items-center p-2 bg-darker-custom mb-2">
                                        <svg width="16" height="16"
                                            viewBox="0 0 24 24" fill="none"
                                            stroke="#9945FF" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round"
                                            aria-hidden="true">
                                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2">
                                            </path>
                                            <circle cx="9" cy="7" r="4">
                                            </circle>
                                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                                        </svg>
                                        <span class="ms-2" style="">${convertLikes(post.reach)} Alcance</span>
                                    </div>
                                    <div style="background-color: #07060E !important; border: 1px solid #E1C8FF26;
                                        border-radius: 5px"
                                        class="d-flex align-items-center p-2 bg-darker-custom mb-2">
                                        <svg width="16" height="16"
                                            viewBox="0 0 24 24" fill="none"
                                            stroke="#9945FF" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round"
                                            aria-hidden="true">
                                            <path
                                                d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z">
                                            </path>
                                        </svg>
                                        <span class="ms-2" style="">${convertLikes(post.saved)} Salvamentos</span>
                                    </div>
                                </div>
                            </div>
                    `);

                instagramMediaContainer.append(a);
            });


        }

    }
    renderPosts()


    function formatData() {
        let data = new Date("2025-04-06 19:59:22");
        let formatada = data.toLocaleDateString("pt-BR");
        return formatada
    }

    function convertLikes(number) {
        if (number < 1000) {
            return number.toString(); // Exibe o número normal
        } else if (number < 1000000) {
            return (number / 1000).toFixed(1).replace(".0", "") + "K"; // Exibe em "K"
        } else {
            return (number / 1000000).toFixed(1).replace(".0", "") + "M"; // Exibe em "M"
        }
    }

    const pagination = instagramPosts.pagination ?? { current_page: 1, last_page: 1 };
    let currentPage = pagination.current_page;
    const totalPage = pagination.last_page;
    const perWindow = 1;
    const paginateContainer = $("#paginate-container");

    function goToPage(page) {
        const url = new URL(window.location.href);
        url.searchParams.set("page", page);
        let newUrl = url.toString();
        if (location.hostname != "localhost") {
            if (newUrl.startsWith('http://')) {
                newUrl = newUrl.replace('http://', 'https://');
            }
        }
        window.location.href = newUrl;
    }

    function createButton({
        label,
        page,
        isActive = false,
        isDisabled = false,
        extraClasses = ""
    }) {

        return $("<button>")
            .attr({
                type: "button",
                disabled: isDisabled
            })
            .addClass(`btn-paginate-button ${isActive ? " active" : ""} ${extraClasses}`)
            .html(label)
            .on("click", () => !isDisabled && goToPage(page));
    }
    function renderPagination() {
        paginateContainer.empty();
        const pages = [];

        pages.push({
            label: `
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" 
                            fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" 
                            stroke-linejoin="round" class="lucide lucide-chevron-left-icon lucide-chevron-left">
                            <path d="m15 18-6-6 6-6"/>
                        </svg>
                    `,
            page: currentPage - 1,
            isDisabled: currentPage === 1,
            extraClasses: `alButton ${currentPage !== 1 ? "text-secondary" : ""}`
        });

        let start = Math.max(1, currentPage - perWindow);
        let end = Math.min(totalPage, currentPage + perWindow);

        if (currentPage === 1) end = Math.min(totalPage, 1 + perWindow * 2);
        if (currentPage === totalPage) start = Math.max(1, totalPage - perWindow * 2);

        if (start > 1) {
            pages.push({
                label: 1,
                page: 1,
            });
            if (start > 2) {
                pages.push({
                    label: '...',
                    page: null,
                    isDisabled: true
                });
            }
        }

        for (let p = start; p <= end; p++) {
            pages.push({
                label: p,
                page: p,
                isActive: p === currentPage,
            });
        }

        if (end < totalPage) {
            if (end < totalPage - 1) {
                pages.push({
                    label: '...',
                    page: null,
                    isDisabled: true
                });
            }
            pages.push({
                label: totalPage,
                page: totalPage
            });
        }

        pages.push({
            label: `
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" 
                            fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" 
                            stroke-linejoin="round" class="lucide lucide-chevron-right-icon lucide-chevron-right">
                            <path d="m9 18 6-6-6-6"/>
                        </svg>
                    `,
            page: currentPage + 1,
            isDisabled: currentPage === totalPage,
            extraClasses: `alButton ${currentPage !== totalPage ? "text-secondary" : ""}`
        });

        pages.forEach(cfg => {
            paginateContainer.append(createButton(cfg));
        });
    }

    renderPagination();

    $("#select-period").on("change", function () {
        window.location.href = "/dashboard/user/profile/instagram?period=" + $(this).val();
    })


    const selectedPosts = [];
    $("#close-modal-select-posts").on("click", function () {
        $("#count-posts-selected").html(`0/60`);
        selectedPosts.length = 0;
    });

    $("#btn-select-posts").on("click", function () {
        const container = $("#container-select_posts");
        $.ajax({
            url: "/dashboard/user/profile/instagram/posts/all",
            method: "get",
            success: function (data) {
                container.html('');
                data.forEach(post => {
                    const div = $('<div>', {
                        class: 'col-6 col-sm-4 p-3 d-flex flex-column align-items-center justify-content-center bg-darker-custom cursor-pointer',
                        html: `
                            <div class="d-flex align-items-center gap-3" style="aspect-ratio: 1 / 1; overflow: hidden">
                                <img src="${post.thumbnail_url ? post.thumbnail_url : post.media_url}"
                                    alt="Campaign Post" style="object-fit: cover;" />
                            </div>
                        `
                    });

                    if (post.selected == 1) {
                        selectedPosts.push(post);
                    }

                    div.hover(
                        function () {
                            if (!$(this).hasClass('active')) {
                                $(this).css('border', '1px solid #3e4e61');
                            }
                        },
                        function () {
                            if (!$(this).hasClass('active')) {
                                $(this).css('border', '1px solid #1f2e41');
                            }
                        }
                    );

                    if (selectedPosts.findIndex(p => p.id == post.id) >= 0) {
                        div.addClass("active");
                        div.css({
                            'border': '3px solid #0054a6',
                        });
                    }
                    div.click(function () {
                        if (selectedPosts.length >= 60) return;

                        if ($(this).hasClass("active")) {
                            $(this).removeClass("active");
                            $(this).css({
                                'border': '1px solid #1f2e41',
                            });
                            selectedPosts.splice(selectedPosts.findIndex(e => e.id == post.id), 1);
                        } else {
                            $(this).addClass("active");
                            $(this).css({
                                'border': '3px solid #0054a6',
                            });
                            selectedPosts.push(post)

                        }


                        $("#count-posts-selected").html(`${selectedPosts.length}/60`);
                    });

                    container.append(div);
                });

            },
            error: function (e) {
                toastr.error(e.responseJSON.message);
            }
        });
    });

    $("#set-selected-posts").on("click", function () {

        $.ajax({
            url: "/dashboard/user/profile/instagram/posts/set",
            method: "post",
            data: JSON.stringify({ content: selectedPosts }),
            headers: {
                'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content'),
                'Content-Type': 'application/json'
            },
            success: function (data) {
                toastr.success(data.message);
                setTimeout(() => {
                    location.reload();
                }, 500);
            },
            error: function (e) {
                toastr.error(e.responseJSON.message);
            }
        });
    });
});
