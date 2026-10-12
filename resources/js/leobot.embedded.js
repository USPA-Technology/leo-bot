//
function load_embedded_leobot(config) {
  // === MERGE CONFIGURATION ===
  const mergedConfig = {
    leobotUrl: config.leobotUrl || "https://leobot.leocdp.com/",
    localStorageKey: config.localStorageKey || "leo_bot_state",
    containerWidth: config.containerWidth || "360px",
    text: {
      header: {
        title: config?.text?.header?.title || "XIN CHÀO!",
        subtitle:
          config?.text?.header?.subtitle || "Chúng tôi sẵn sàng hỗ trợ bạn!",
      },
      form: {
        title:
          config?.text?.form?.title ||
          "Bạn vui lòng điền thông tin để kết nối đến chuyên viên tư vấn hỗ trợ:",
        name: config?.text?.form?.name || "Họ và tên*",
        phone: config?.text?.form?.phone || "Số điện thoại*",
        email: config?.text?.form?.email || "Địa chỉ email",
        question: config?.text?.form?.question || "Câu hỏi của bạn*",
        submit: config?.text?.form?.submit || "Gửi thông tin",
      },
      toggleButtonText: config?.text?.toggleButtonText || "💬 Chat",
    },
  };

  // === RESTORE STATE FROM LOCALSTORAGE ===
  let savedState = {};
  try {
    savedState =
      JSON.parse(localStorage.getItem(mergedConfig.localStorageKey)) || {};
  } catch (e) {}

  function saveState(newState) {
    const updated = { ...savedState, ...newState };
    localStorage.setItem(mergedConfig.localStorageKey, JSON.stringify(updated));
    savedState = updated;
  }

  // === CREATE TOGGLE BUTTON ===
  const toggleBtn = document.createElement("div");
  toggleBtn.innerHTML = mergedConfig.text.toggleButtonText;
  Object.assign(toggleBtn.style, {
    position: "fixed",
    bottom: "20px",
    left: "20px",
    zIndex: "9999",
    backgroundColor: "#0d6efd",
    color: "#fff",
    padding: "10px 16px",
    borderRadius: "30px",
    cursor: "pointer",
    fontSize: "16px",
    fontFamily: "Arial, sans-serif",
    boxShadow: "0 4px 8px rgba(0,0,0,0.2)",
    transition: "opacity 0.3s ease",
  });
  document.body.appendChild(toggleBtn);

  // === CREATE POPUP CONTAINER ===
  const container = document.createElement("div");
  Object.assign(container.style, {
    position: "fixed",
    bottom: "80px",
    left: "20px",
    width: mergedConfig.containerWidth,
    zIndex: "9998",
    fontFamily: "Arial, sans-serif",
    boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
    borderRadius: "10px",
    overflow: "hidden",
    backgroundColor: "#fff",
    display: savedState.isOpen ? "block" : "none",
  });

  // === HEADER ===
  const header = document.createElement("div");
  header.innerHTML = `
    <div style="background: linear-gradient(135deg, #005bea 0%, #00c6fb 100%);
                color: white; padding: 16px; display: flex; align-items: center; justify-content: space-between;">
      <div style="display:flex; align-items:center;">
        <div style="background: white; border-radius: 8px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; margin-right: 10px;">
          <img src="https://cdn-icons-png.flaticon.com/512/684/684908.png" width="20" />
        </div>
        <div>
          <div style="font-weight: bold; font-size: 14px;">${mergedConfig.text.header.title}</div>
          <div style="font-size: 12px;">${mergedConfig.text.header.subtitle}</div>
        </div>
      </div>
      <div style="cursor: pointer; font-size: 18px;"
           onclick="this.closest('div').parentElement.style.display='none'; localStorage.setItem('${mergedConfig.localStorageKey}', JSON.stringify({...JSON.parse(localStorage.getItem('${mergedConfig.localStorageKey}') || '{}'), isOpen: false}))">×</div>
    </div>
  `;

  // === CONTACT FORM ===
  const formContainer = document.createElement("div");
  formContainer.style.padding = "16px";
  formContainer.style.display = savedState.isSubmitted ? "none" : "block";
  formContainer.innerHTML = `
    <div style="font-size: 14px; margin-bottom: 10px;">
      ${mergedConfig.text.form.title}
    </div>
    <form id="leo_contact_form" style="display:flex; flex-direction:column; gap:8px;">
      <input required placeholder="${mergedConfig.text.form.name}" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:6px;" />
      <input required placeholder="${mergedConfig.text.form.phone}" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:6px;" />
      <input type="email" placeholder="${mergedConfig.text.form.email}" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:6px;" />
      <textarea required placeholder="${mergedConfig.text.form.question}" rows="3" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:6px;"></textarea>
      <button type="submit" style="align-self:flex-end; min-width:120px; width:auto; padding:10px 16px; background:#005bea; color:white; border:none; border-radius:6px; font-weight:bold; cursor:pointer;">${mergedConfig.text.form.submit}</button>
    </form>
  `;

  // === CHATBOT IFRAME ===
  const iframe = document.createElement("iframe");
  Object.assign(iframe.style, {
    display: savedState.isSubmitted ? "block" : "none",
    width: "100%",
    height: "500px",
    border: "none",
  });

  // Compute iframe URL with hash if savedState is non-empty
  const isNonEmptyState = savedState && Object.keys(savedState).length > 0;
  iframe.src = isNonEmptyState
    ? `${mergedConfig.leobotUrl}#${encodeURIComponent(
        JSON.stringify(savedState)
      )}`
    : mergedConfig.leobotUrl;

  iframe.title = "LEO Bot";

  // === FORM SUBMIT HANDLER ===
  formContainer
    .querySelector("#leo_contact_form")
    .addEventListener("submit", function (e) {
      e.preventDefault();
      formContainer.style.display = "none";
      iframe.style.display = "block";
      saveState({ isSubmitted: true });
    });

  // === TOGGLE BUTTON HANDLER ===
  toggleBtn.addEventListener("click", function () {
    const isVisible = container.style.display === "block";
    container.style.display = isVisible ? "none" : "block";
    saveState({ isOpen: !isVisible });
  });

  // === ASSEMBLE ===
  container.appendChild(header);
  container.appendChild(formContainer);
  container.appendChild(iframe);
  document.body.appendChild(container);
}
