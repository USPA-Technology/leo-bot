// Keep profile and enrichment-refresh state together for each chat page.
class ChatbotState {
  constructor() {
    this.profile = {
      visitorId: "",
      displayName: "friend",
      touchpointId: "",
      latitude: null,
      longitude: null,
    };
    this.latestUserQuestion = "";
    this.latestUserQuestionVersion = 0;
    this.lastEnrichmentRefreshVersion = 0;
  }

  rememberQuestion(question, isRefresh) {
    if (isRefresh) return;
    this.latestUserQuestion = question;
    this.latestUserQuestionVersion += 1;
  }

  getQuestionToRefresh() {
    if (
      !this.latestUserQuestion ||
      this.lastEnrichmentRefreshVersion === this.latestUserQuestionVersion
    ) {
      return null;
    }
    return this.latestUserQuestion;
  }

  markQuestionRefreshed() {
    this.lastEnrichmentRefreshVersion = this.latestUserQuestionVersion;
  }
}

var chatbotState = new ChatbotState();
var currentUserProfile = chatbotState.profile;

// Retain one BotUI instance while keeping initialization behind a small facade.
class ChatbotUI {
  get() {
    if (window.leoBotUI === false) {
      window.leoBotUI = new BotUI("LEO_ChatBot_Container");
    }
    return window.leoBotUI;
  }

  initialize() {
    window.leoBotUI = new BotUI("LEO_ChatBot_Container");
    return window.leoBotUI;
  }
}

var chatbotUI = new ChatbotUI();

// --- Localization and host-page events ---
function getLeoUiText(key, fallback) {
  if (typeof window.leoUiText === "function") {
    return window.leoUiText(key);
  }
  return fallback;
}

function getLeoUiLanguage() {
  return window.LEO_UI_LANGUAGE === "en" ? "en" : "vi";
}


function loadChatSessionWithProfile() {
  let userProfile = {};
  const hashData = location.hash.substring(1);
  try {
    userProfile = hashData ? JSON.parse(decodeURIComponent(hashData)) : {};
    console.log("Loaded user profile from hash:", userProfile);
  } catch (e) {
    console.warn("Invalid profile data in hash:", e);
    userProfile = {};
  }

  // === You can now use `userProfile` to personalize the chatbot ===
  // Example:
  // if (userProfile.name) greetUser(userProfile.name);
}

// Refresh optional chat profile data when the host page changes its hash.
$(window).on("hashchange", loadChatSessionWithProfile);

window.leoBotUI = false;
window.leoBotContext = false;

// Return the lazily initialized BotUI view.
function getBotUI() {
  return chatbotUI.get();
}

// --- Visitor location and touchpoint ---
// Build the browser-cache key for one visitor's touchpoint.
function touchpointCacheKey(visitorId) {
  return "touchpoint_id_" + visitorId;
}

// Publish geolocation transitions to other UI components.
function emitLocationState(state, data) {
  $(document).trigger("leo:location", [
    { state: state, data: data || null },
  ]);
}

// Resolve browser location and persist it as a chat touchpoint.
function requestUserGeolocation(visitorId, forceRefresh) {
  if (!navigator.geolocation || typeof BASE_URL_TOUCHPOINT === "undefined") {
    emitLocationState("unavailable");
    return Promise.resolve(null);
  }

  emitLocationState("requesting");
  return new Promise(function (resolve) {
    navigator.geolocation.getCurrentPosition(
      function (position) {
        var payload = {
          visitor_id: visitorId,
          name: document.title || "Web visitor",
          description: "Browser geolocation touchpoint",
          type: "web",
          keywords: [window.location.hostname],
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          touchpoint_id:
            currentUserProfile.touchpointId ||
            lscache.get(touchpointCacheKey(visitorId)) ||
            null,
        };
        $.ajax({
          url: BASE_URL_TOUCHPOINT,
          type: "POST",
          contentType: "application/json",
          data: JSON.stringify(payload),
        })
          .done(function (data) {
            data.accuracy = position.coords.accuracy;
            currentUserProfile.touchpointId = data.touchpoint_id || "";
            currentUserProfile.latitude = data.latitude;
            currentUserProfile.longitude = data.longitude;
            if (currentUserProfile.touchpointId) {
              lscache.set(
                touchpointCacheKey(visitorId),
                currentUserProfile.touchpointId
              );
            }
            console.info("Location-aware touchpoint ready", data.touchpoint_id);
            emitLocationState("ready", data);
            resolve(data);
          })
          .fail(function () {
            console.warn("Unable to create location touchpoint.");
            emitLocationState("error");
            resolve(null);
          });
      },
      function (error) {
        console.info("Geolocation unavailable or denied:", error.message);
        emitLocationState(
          error.code === error.PERMISSION_DENIED
            ? "denied"
            : error.code === error.POSITION_UNAVAILABLE
              ? "unavailable"
              : "error"
        );
        resolve(null);
      },
      {
        enableHighAccuracy: Boolean(forceRefresh),
        maximumAge: forceRefresh ? 0 : 300000,
        timeout: 10000,
      }
    );
  });
}

// Initialize visitor state, resolve location, and load the greeting profile.
function initLeoChatBot(context, visitorId, okCallback) {
  window.leoBotContext = context;
  window.currentUserProfile.visitorId = visitorId;
  currentUserProfile.touchpointId =
    lscache.get(touchpointCacheKey(visitorId)) || "";
  chatbotUI.initialize();

  loadChatSessionWithProfile();
  requestUserGeolocation(visitorId).catch(function (error) {
    console.warn("Unable to resolve visitor geolocation:", error);
    emitLocationState("error");
  });
  $.getJSON(BASE_URL_GET_VISITOR_INFO, {
      visitor_id: visitorId,
      _: Date.now(),
    })
    .then(null, function () {
      return { error_code: 500 };
    })
    .then(function (data) {
    console.log(data);

    if (data.error_code === 0 && typeof data.name === "string") {
      currentUserProfile.displayName = data.name;
      showLeoChatBot(currentUserProfile.displayName);
    } else if (data.error_code === 404) {
      currentUserProfile.displayName = "";
      showLeoChatBot(currentUserProfile.displayName);
    } else {
      leoBotShowError(data, leoBotPromptQuestion);
    }
  });

  if (typeof okCallback === "function") {
    okCallback();
  }
}

// Build the localized greeting shown when a chat session starts.
function getGreetingMessage(displayName, language) {
  switch (language) {
    case "vi":
      return "Chào " + displayName + ", bạn có thể hỏi tôi bất cứ điều gì";
    case "en":
    default:
      return "Hi " + displayName + ", you may ask me for anything";
  }
}

// Show the greeting and then prompt the visitor for their first question.
var showLeoChatBot = function (displayName) {
  var msg = getGreetingMessage(displayName, getLeoUiLanguage());
  var msgObj = { content: msg, cssClass: "leobot-answer" };
  getBotUI().message.removeAll();
  getBotUI().message.bot(msgObj).then(leoBotPromptQuestion);
};

// --- Message rendering ---
// Add the next text prompt and route its answer to the chat API.
var leoBotPromptQuestion = function (delay) {
  getBotUI()
    .action.text({
      delay: typeof delay === "number" ? delay : 800,
      action: {
        cssClass: "leobot-question-input",
        value: "", // show the prevous answer if any
        placeholder: getLeoUiText("chatPlaceholder", "What would you like to find?"),
      },
    })
    .then(function (res) {
      sendQuestionToLeoAI("ask", res.value);
    });
};

// Turn nearby-place list items into safe, searchable Google links.
function linkNearbyPlaceNames(container, rawAnswer) {
  var $chatContainer = $("#LEO_ChatBot_Container");
  if (
    !$chatContainer.length ||
    $chatContainer.attr("data-place-search-links") !== "true" ||
    !/^(?:Nearby\b.+:|Các\s+.+\s+gần bạn:)/i.test(rawAnswer.trim())
  ) {
    return;
  }

  $(container).find("ol > li").each(function () {
    var item = this;
    var $item = $(item);
    if ($item.find("a").length) return;

    var text = $item.text().replace(/\s+/g, " ").trim();
    var match = text.match(
      /^(.+?)\s+\((?:\d+(?:\.\d+)?\s*m|distance unavailable)\)(?:\s+-\s+(.+))?$/i
    );
    if (!match) return;

    var placeName = match[1].trim();
    var address = match[2]
      ? match[2].split(/\s+-\s+/)[0].trim()
      : "";
    var query = address ? placeName + " " + address : placeName;
    var $link = $("<a>")
      .addClass("leobot-place-search-link")
      .attr({
        href: "https://www.google.com/search?q=" + encodeURIComponent(query),
        target: "_blank",
        rel: "noopener noreferrer",
      })
      .text(placeName);

    var walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT);
    var textNode;
    while ((textNode = walker.nextNode())) {
      var nameStart = textNode.textContent.indexOf(placeName);
      if (nameStart < 0) continue;

      var replacement = document.createDocumentFragment();
      replacement.appendChild(
        document.createTextNode(textNode.textContent.slice(0, nameStart))
      );
      replacement.appendChild($link[0]);
      replacement.appendChild(
        document.createTextNode(
          textNode.textContent.slice(nameStart + placeName.length)
        )
      );
      textNode.parentNode.replaceChild(replacement, textNode);
      break;
    }
  });
}

// Render an API response as a BotUI-ready node.
var processMessageNode = function (rawAnswer) {
  var nodeId = "m_" + getRandomStrWithTime();
  if (rawAnswer.indexOf("<html>") >= 0) {
    var $iframe = $("<iframe>")
      .attr("id", nodeId)
      .css({
        width: "100%",
        height: "400px",
        border: "1px solid #ddd",
        borderRadius: "6px",
      });

    return { html: $iframe.prop("outerHTML"), type: "iframe", id: nodeId };
  }

  var $container = $("<div>")
    .attr("id", nodeId)
    .html(marked.parse(rawAnswer));
  linkNearbyPlaceNames($container[0], rawAnswer);
  return { html: $container.prop("outerHTML"), type: "div", id: nodeId };
};

// Generate a unique DOM id for each rendered answer.
function getRandomStrWithTime(length = 10) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const randomPart = Array.from({ length }, function () {
    return chars.charAt(Math.floor(Math.random() * chars.length));
  }).join("");
  const timestamp = Date.now().toString(36);
  return randomPart + "_" + timestamp;
}

// Render the answer and schedule the next chat prompt.
var leoBotShowAnswer = function (rawAnswer, providedDelay) {
  var node = processMessageNode(rawAnswer);
  getBotUI()
    .message.add({
      human: false,
      cssClass: "leobot-answer",
      content: node.html,
      type: "html",
    })
    .then(function () {
      if (node.type === "iframe") {
        var iframe = document.getElementById(node.id);
        var iframeDocument =
          iframe.contentDocument || iframe.contentWindow.document;
        iframeDocument.open();
        iframeDocument.write(rawAnswer);
        iframeDocument.close();

        $(iframe)
          .parent()
          .parent()
          .removeClass("botui-message-content")
          .addClass("botui-message-report");
      }

      $("div.botui-message")
        .find("a")
        .each(function () {
          $(this).attr("target", "_blank");
          $(this).attr("rel", "noopener noreferrer");
          var href = $(this).attr("href") || "";
          if (href.indexOf("google.com") < 0) {
            href =
              "https://www.google.com/search?q=" +
              encodeURIComponent($(this).text());
          }
          $(this).attr("href", href);
        });

      let delay;
      if (typeof providedDelay === "number") {
        delay = providedDelay;
      } else if (rawAnswer.length > 200) {
        delay = 3000;
      } else {
        delay = 1500;
      }
      leoBotPromptQuestion(delay);
    });
};

// Render an error and resume the prompt flow when requested.
var leoBotShowError = function (error, nextAction) {
  getBotUI()
    .message.add({
      human: false,
      cssClass: "leobot-error",
      content: error,
      type: "html",
    })
    .then(nextAction || function () {});
};

// --- Optional profile collection ---
// Validate an email address before starting profile registration.
function isEmailValid(email) {
  const regex =
    /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
  return regex.test(email);
}

var askTheEmailOfUser = function (name) {
  getBotUI()
    .action.text({
      delay: 0,
      action: {
        icon: "envelope-o",
        cssClass: "leobot-question-input",
        value: "",
        placeholder: "Email của bạn",
      },
    })
    .then(function (res) {
      var email = res.value;
      if (isEmailValid(email)) {
        console.log(name, email);
        var profileData = {
          loginProvider: "leochatbot",
          firstName: name,
          email: email,
        };
        if (window.CDP_TRACKING === true) {
          LeoObserverProxy.updateProfileBySession(profileData);
        }

        setTimeout(function () {
          location.reload(true);
        }, 3000);

        var message =
          "Chào " + name + ", hệ thống đang đăng ký thông tin cho bạn ...";
        leoBotShowAnswer(message, 6000);
      } else {
        leoBotShowError(email + " không là email hợp lệ", function () {
          askTheEmailOfUser(name);
        });
      }
    });
};

var askTheNameOfUser = function () {
  getBotUI()
    .action.text({
      delay: 0,
      action: {
        icon: "user-circle-o",
        cssClass: "leobot-question-input",
        value: "",
        placeholder: "Tên bạn",
      },
    })
    .then(function (res) {
      askTheEmailOfUser(res.value);
    });
};

var askTheContactOfUser = function () {
  var msg = "Chào bạn, vui lòng nhập tên và email để  cần hỗ trỡ";
  getBotUI()
    .message.add({
      human: false,
      cssClass: "leobot-question",
      content: msg,
      type: "html",
    })
    .then(askTheNameOfUser);
};

// --- Chat requests and enrichment status ---
// Coordinate question state, API requests, and enrichment subscriptions.
class ChatbotController {
  constructor(state) {
    this.state = state;
  }

  sendQuestion(context, question, isEnrichmentRefresh) {
    question = typeof question === "string" ? question.trim() : "";
    if (!question) {
      leoBotShowError(
        getLeoUiText(
          "emptyQuestion",
          "Please enter a question or a place number."
        ),
        leoBotPromptQuestion
      );
      return;
    }
    if (question === "exit") return;

    this.state.rememberQuestion(question, isEnrichmentRefresh);

    var processAnswer = function (answer) {
      if (context === "ask") {
        leoBotShowAnswer(answer);
      }
      if (typeof LeoObserver === "object" && CDP_TRACKING === true) {
        var eventData = { question: question, answer: answer.slice(0, 1000) };
        LeoObserver.recordEventAskQuestion(eventData);
      } else {
        console.log("SKIP LeoObserver.recordEventAskQuestion");
      }
    };

    var callServer = function (index) {
      var serverCallback = function (data) {
        getBotUI().message.remove(index);
        var errorCode = data.error_code;
        var answer = data.answer;
        if (errorCode === 0) {
          currentUserProfile.displayName =
            data.name || currentUserProfile.displayName;
          if (data.touchpoint_id) {
            currentUserProfile.touchpointId = data.touchpoint_id;
            lscache.set(
              touchpointCacheKey(currentUserProfile.visitorId),
              data.touchpoint_id
            );
          }
          processAnswer(answer);
          if (Array.isArray(data.similar_places) &&
              data.similar_places.length > 0 &&
              data.similar_places_answer) {
            processAnswer(data.similar_places_answer);
          }
          if (data.enrichment_status_url) {
            watchGeoPlacesEnrichment(data.enrichment_status_url);
          }
        } else if (errorCode === 404) {
          currentUserProfile.displayName = "";
          processAnswer(answer);
        } else {
          leoBotShowError(answer, leoBotPromptQuestion);
        }
      };

      var conversationContext = $(
        "#LEO_ChatBot_Container .botui-message-content"
      )
        .slice(-3)
        .map(function (index, message) {
          return message.textContent;
        })
        .get()
        .join(" ; ");

      var payload = {
        context: conversationContext,
        question: question,
        visitor_id: currentUserProfile.visitorId,
        touchpoint_id: currentUserProfile.touchpointId || null,
        latitude: currentUserProfile.latitude,
        longitude: currentUserProfile.longitude,
        answer_in_language:
          getLeoUiLanguage() === "en" ? "English" : "Vietnamese",
        answer_in_format: "html",
      };

      callPostApi(BASE_URL_LEOBOT, payload, serverCallback, function () {
        getBotUI().message.remove(index);
        leoBotShowError(
          getLeoUiText(
            "networkError",
            "Unable to send your message. Please try again."
          ),
          leoBotPromptQuestion
        );
      });
    };

    showChatBotLoader().then(callServer);
  }
}

var chatbotController = new ChatbotController(chatbotState);

// Keep the global function used by BotUI prompts and external page scripts.
var sendQuestionToLeoAI = function (context, question, isEnrichmentRefresh) {
  chatbotController.sendQuestion(context, question, isEnrichmentRefresh);
};

var showChatBotLoader = function () {
  return getBotUI().message.add({ loading: true, content: "" });
};


// Own the SSE lifecycle and translate Dagster states into chat messages.
class GeoPlacesEnrichmentWatcher {
  constructor(state, uiProvider, questionSender) {
    this.state = state;
    this.uiProvider = uiProvider;
    this.questionSender = questionSender;

    this.terminalStatuses = ["SUCCESS", "FAILURE", "CANCELED"];

    this.messages = {
      QUEUED: {
        text: [
          "Place search added to queue.",
          "Yêu cầu tìm địa điểm đã được đưa vào hàng đợi.",
        ],
        icon: "bi-hourglass-split",
        color: "info",
      },
      NOT_STARTED: {
        text: [
          "Place search hasn't started.",
          "Tìm kiếm địa điểm chưa bắt đầu.",
        ],
        icon: "bi-hourglass-split",
        color: "info",
      },
      MANAGED: {
        text: [
          "Waiting for a worker.",
          "Đang chờ worker xử lý.",
        ],
        icon: "bi-hourglass-split",
        color: "info",
      },
      STARTING: {
        text: [
          "Starting place search…",
          "Đang khởi tạo tìm kiếm địa điểm…",
        ],
        icon: "bi-arrow-repeat",
        color: "info",
        loading: true,
      },
      STARTED: {
        text: [
          "Searching nearby places…",
          "Đang tìm địa điểm gần bạn…",
        ],
        icon: "bi-geo-alt-fill",
        color: "primary",
        loading: true,
      },
      CANCELING: {
        text: [
          "Canceling place search…",
          "Đang hủy tìm kiếm địa điểm…",
        ],
        icon: "bi-x-circle",
        color: "warning",
      },
      SUCCESS: {
        text: [
          "Places updated. Ask again for results.",
          "Địa điểm đã được cập nhật. Hãy hỏi lại để xem kết quả.",
        ],
        icon: "bi-check-circle-fill",
        color: "success",
      },
      PLACES_READY: {
        text: [
          "Place discovery finished. Checking saved results.",
          "Đã hoàn tất tìm kiếm địa điểm. Đang kiểm tra kết quả đã lưu.",
        ],
        icon: "bi-check-circle-fill",
        color: "success",
      },
      FAILURE: {
        text: [
          "Place search failed. Try again later.",
          "Tìm kiếm địa điểm thất bại. Vui lòng thử lại sau.",
        ],
        icon: "bi-exclamation-triangle-fill",
        color: "danger",
      },
      CANCELED: {
        text: [
          "Place search canceled.",
          "Đã hủy tìm kiếm địa điểm.",
        ],
        icon: "bi-x-circle",
        color: "warning",
      },
      STATUS_UNAVAILABLE: {
        text: [
          "Search status unavailable. Try again later.",
          "Không thể kiểm tra trạng thái tìm kiếm. Vui lòng thử lại sau.",
        ],
        icon: "bi-exclamation-circle-fill",
        color: "warning",
      },
    };

    this.refreshSuccessMessages = [
      "Places updated; checking your latest question…",
      "Địa điểm đã cập nhật; đang xử lý câu hỏi mới nhất…",
    ];
  }

  // Add a localized chat message for one Dagster status.
  showStatus(status, willRefreshResults) {
    let statusMessage = this.messages[status];

    if (!statusMessage) {
      console.warn("Unknown geo-place enrichment status:", status);
      statusMessage = this.messages.STATUS_UNAVAILABLE;
    }

    const language = getLeoUiLanguage();
    const languageIndex = language === "en" ? 0 : 1;

    const localizedMessage =
      (status === "SUCCESS" || status === "PLACES_READY") && willRefreshResults
        ? this.refreshSuccessMessages[languageIndex]
        : statusMessage.text[languageIndex];

    // Use Bootstrap's animated spinner for active processing states.
    const statusIcon = statusMessage.loading
      ? '<span class="spinner-border spinner-border-sm flex-shrink-0" ' +
        'aria-hidden="true"></span>'
      : '<i class="bi ' +
        statusMessage.icon +
        ' fs-5 flex-shrink-0" aria-hidden="true"></i>';

    this.uiProvider().message.add({
      human: false,
      cssClass: "leobot-answer geo-enrichment-status",
      content:
        '<div class="alert alert-' +
        statusMessage.color +
        ' d-flex align-items-center gap-2 py-2 px-3 mb-0" role="status">' +
        statusIcon +
        "<span>" +
        localizedMessage +
        "</span>" +
        "</div>",
      type: "html",
    });
  }

  // Subscribe to status updates for one enrichment run.
  watch(statusUrl) {
    if (!statusUrl) return;
    if (typeof EventSource !== "function") {
      this.showStatus("STATUS_UNAVAILABLE");
      return;
    }

    var eventSource = new EventSource(
      new URL(statusUrl, BASE_URL_LEOBOT).toString()
    );
    eventSource.onmessage = (event) => this.handleMessage(eventSource, event);
    eventSource.addEventListener("status_error", () => {
      eventSource.close();
      this.showStatus("STATUS_UNAVAILABLE");
    });
  }

  // Handle a status event and refresh the latest question once on success.
  handleMessage(eventSource, event) {
    var update;
    try {
      update = JSON.parse(event.data);
    } catch (error) {
      console.error("Invalid geo-place enrichment status event", error);
      eventSource.close();
      this.showStatus("STATUS_UNAVAILABLE");
      return;
    }

    if (!update || typeof update.status !== "string") {
      eventSource.close();
      this.showStatus("STATUS_UNAVAILABLE");
      return;
    }

    var placesReady =
      update.status === "SUCCESS" || update.status === "PLACES_READY";
    var refreshQuestion =
      placesReady ? this.state.getQuestionToRefresh() : null;
    this.showStatus(update.status, Boolean(refreshQuestion));
    if (placesReady || this.terminalStatuses.indexOf(update.status) >= 0) {
      eventSource.close();
    }
    if (refreshQuestion) {
      this.state.markQuestionRefreshed();
      this.questionSender("ask", refreshQuestion, true);
    }
  }
}

// Share the state and UI adapters with the enrichment monitor.
var enrichmentWatcher = new GeoPlacesEnrichmentWatcher(
  chatbotState,
  function () {
    return getBotUI();
  },
  function (context, question, isRefresh) {
    sendQuestionToLeoAI(context, question, isRefresh);
  }
);

// Preserve the existing global helpers used by pages and tests.
function showGeoEnrichmentStatus(status, willRefreshResults) {
  enrichmentWatcher.showStatus(status, willRefreshResults);
}

function watchGeoPlacesEnrichment(statusUrl) {
  enrichmentWatcher.watch(statusUrl);
}

// Send a JSON request and dispatch its success or failure callback.
var callPostApi = function (urlStr, data, okCallback, errorCallback) {
  $.ajax({
    url: urlStr,
    crossDomain: true,
    data: JSON.stringify(data),
    contentType: "application/json",
    type: "POST",
    error: function (jqXHR, exception) {
      console.error("WE GET AN ERROR AT URL:" + urlStr);
      console.error(exception);
      if (typeof errorCallback === "function") {
        errorCallback();
      }
    },
  }).done(function (json) {
    okCallback(json);
    console.log("callPostApi", urlStr, data, json);
  });
};

// Generate an RFC 4122 version 4 visitor identifier.
function generateUUID() {
  return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
    (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
  );
}

// Reuse a visitor ID from local storage, creating one when needed.
async function getVisitorId(ttlDays = 365) {
  let id = lscache.get("visitor_id");

  if (!id) {
    id = generateUUID();

    // Store with TTL (days)
    lscache.set("visitor_id", id);

    // Keep a cookie fallback for hosts without local-storage persistence.
    document.cookie = `visitor_id=${id}; path=/; max-age=${ttlDays * 24 * 60 * 60}`;
  }

  return id;
}


// Reveal the chatbot, create its visitor session, and initialize its UI.
var startLeoChatBot = function (visitorId) {
  if (window.leoBotStarted === true) return;
  window.leoBotStarted = true;
  lscache.setBucket("leobot");

  var setupChatBot = function (id) {
    currentUserProfile.visitorId = id;
    $("#LEO_ChatBot_Container_Loader")
      .stop(true, true)
      .removeClass("d-flex")
      .addClass("d-none")
      .hide();
    $("#LEO_ChatBot_Container")
      .stop(true, true)
      .show()
      .css("opacity", "1");
    initLeoChatBot("leobot_website", id);
  };

  if (visitorId === undefined) {
    getVisitorId().then(function (id) {
      console.log("startLeoChatBot with Visitor ID:", id);
      setupChatBot(id);
    });
    return;
  }

  console.log("startLeoChatBot with Visitor ID:", visitorId);
  setupChatBot(visitorId);
};
