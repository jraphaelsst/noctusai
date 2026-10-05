
function creditsBadge() {
    return {
        balance: null,

        init() {
            this.fetch();
            setInterval(() => this.fetch(), 30000);
        },

        async fetch() {
            try {
                const res = await fetch('https://corestudio.ai/dashboard/user/twin/api/credits', {
                    headers: { Accept: 'application/json' },
                });

                if (!res.ok) return;

                const json = await res.json();
                this.balance = json.balance;
                this.$el.classList.toggle('is-empty', json.balance < json.cost_per_minute);
            } catch (e) {
                console.error('[CreditsBadge] Erro ao buscar saldo:', e);
            }
        },
    };
}

function notificationsDropdown() {
    return {
        open: false,
        showRead: false,
        notifications: [],
        unreadCount: 0,
        readCount: 0,

        init() {
            this.fetch();
            setInterval(() => this.fetch(), 30000);
        },

        toggle() {
            this.open = !this.open;
            if (this.open) this.fetch();
        },

        toggleShowRead() {
            this.showRead = !this.showRead;
            this.fetch();
        },

        async fetch() {
            try {
                const url = new URL('https://corestudio.ai/dashboard/user/notifications', window.location.origin);
                if (this.showRead) url.searchParams.set('show_read', '1');
                const res = await fetch(url, {
                    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await res.json();
                this.notifications = data.notifications;
                this.unreadCount = data.unread_count;
                this.readCount = data.read_count;
            } catch (e) {
                console.error('[Notifications] Erro ao buscar:', e);
            }
        },

        async markRead(n) {
            if (n.status === 1) return;
            n.status = 1;
            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.readCount++;
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            await fetch(`/dashboard/user/notifications/${n.id}/read`, {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': token, 'Accept': 'application/json' }
            });
        },

        async markAllRead() {
            this.readCount += this.notifications.filter(n => n.status === 0).length;
            this.notifications = this.showRead
                ? this.notifications.map(n => ({ ...n, status: 1 }))
                : [];
            this.unreadCount = 0;
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            await fetch('https://corestudio.ai/dashboard/user/notifications/read-all', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': token, 'Accept': 'application/json' }
            });
        },

        timeAgo(dateStr) {
            const now = new Date();
            const date = new Date(dateStr);
            const diff = Math.floor((now - date) / 1000);
            if (diff < 60) return 'agora';
            if (diff < 3600) return Math.floor(diff / 60) + ' min atrás';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h atrás';
            if (diff < 604800) return Math.floor(diff / 86400) + 'd atrás';
            return date.toLocaleDateString('pt-BR');
        }
    }
}
