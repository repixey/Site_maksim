document.addEventListener('DOMContentLoaded', () => {
  const chatToggle = document.getElementById('chat-toggle');
  const chatPanel = document.getElementById('chat-panel');
  const chatClose = document.getElementById('chat-close');
  const chatForm = document.getElementById('chat-form');
  const chatInput = chatForm ? chatForm.querySelector('.chat-panel__input') : null;
  const chatBody = document.querySelector('.chat-panel__body');

  const ROOM = 'support'; // Комната по умолчанию для виджета

  if (!chatToggle || !chatPanel) return;

  // Открытие / закрытие панели
  chatToggle.addEventListener('click', () => {
    chatPanel.hidden = !chatPanel.hidden;
    if (!chatPanel.hidden) {
      if (chatInput) chatInput.disabled = false;
      loadWidgetMessages();
    }
  });

  if (chatClose) {
    chatClose.addEventListener('click', () => {
      chatPanel.hidden = true;
    });
  }

  // Загрузка сообщений в виджет
  async function loadWidgetMessages() {
    if (!chatBody) return;
    try {
      const res = await fetch(`/api/chat/${ROOM}/messages`);
      if (!res.ok) return;

      const messages = await res.json();
      chatBody.innerHTML = '';

      if (messages.length === 0) {
        chatBody.innerHTML = '<div class="chat-msg chat-msg--in">Задайте ваш вопрос!</div>';
        return;
      }

      messages.forEach(msg => {
        const div = document.createElement('div');
        div.className = `chat-msg ${msg.is_admin ? 'chat-msg--in' : 'chat-msg--out'}`;
        div.textContent = `${msg.sender_name}: ${msg.message}`;
        chatBody.appendChild(div);
      });

      chatBody.scrollTop = chatBody.scrollHeight;
    } catch (e) {
      console.error('Ошибка виджета чата:', e);
    }
  }

  // Отправка сообщения из виджета
  if (chatForm) {
    chatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!chatInput) return;
      const text = chatInput.value.trim();
      if (!text) return;

      try {
        const res = await fetch(`/api/chat/${ROOM}/send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });

        if (res.ok) {
          chatInput.value = '';
          loadWidgetMessages();
        }
      } catch (e) {
        console.error('Ошибка отправки из виджета:', e);
      }
    });
  }

  // Обновляем сообщения каждые 4 секунды, если виджет открыт
  setInterval(() => {
    if (!chatPanel.hidden) {
      loadWidgetMessages();
    }
  }, 4000);
});