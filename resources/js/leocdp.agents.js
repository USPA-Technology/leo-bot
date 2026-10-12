(function ($, window, document) {
  "use strict";

  window.LEO_UI_TEXTS = {
    vi: {
      help: "Trợ giúp",
      exploreWithContext: "Khám phá theo ngữ cảnh",
      heroTitle: "Khám phá địa điểm cùng LEO",
      heroDescription: "Hỏi về các địa điểm gần bạn, nhận gợi ý địa phương hoặc tiếp tục trò chuyện về địa điểm bạn đã chọn.",
      heroDescriptionMobile: "Khám phá địa điểm gần bạn cùng LEO.",
      locationHelps: "Vị trí giúp LEO hữu ích hơn",
      locationPrivacy: "Trình duyệt sẽ hỏi quyền truy cập. Chúng tôi chỉ dùng vị trí để tìm địa điểm gần bạn, không dùng để theo dõi.",
      chatWithLeo: "Trò chuyện với LEO",
      online: "Đang trực tuyến",
      chatHint: "Thử “quán cà phê gần tôi” hoặc chọn một gợi ý.",
      locationOff: "Đã tắt vị trí",
      preparingAssistant: "Đang chuẩn bị trợ lý địa phương…",
      yourContext: "Ngữ cảnh của bạn",
      currentLocation: "Vị trí hiện tại",
      checkingLocation: "Đang kiểm tra khả năng truy cập vị trí…",
      coordinates: "Tọa độ",
      notAvailable: "Chưa có dữ liệu",
      accuracy: "Độ chính xác",
      available: "Có dữ liệu",
      language: "Ngôn ngữ",
      useMyLocation: "Dùng vị trí của tôi",
      refreshLocation: "Làm mới vị trí",
      gettingLocation: "Đang lấy vị trí…",
      permissionHint: "Bạn có thể thay đổi quyền này trong cài đặt trình duyệt.",
      startExploring: "Bắt đầu khám phá",
      whatLookingFor: "Bạn đang tìm gì?",
      loadingRecommendations: "Đang tải gợi ý gần bạn…",
      locationSuggestionsUnavailable: "Cho phép vị trí để tải gợi ý gần bạn.",
      nearbyHint: "LEO sẽ dùng vị trí của bạn khi tìm kiếm địa điểm gần đó.",
      madeBy: "Phát triển bởi",
      privateByDesign: "· Riêng tư theo thiết kế",
      locationOptional: "Dịch vụ vị trí là tùy chọn.",
      helpTitle: "Sử dụng LEO hiệu quả hơn",
      helpDescription: "Hãy hỏi tự nhiên. Để khám phá địa điểm, hãy thêm “gần tôi” và cho phép truy cập vị trí khi được hỏi.",
      helpExampleOne: "“Tìm nhà thờ gần nhất”",
      helpExampleTwo: "“Gần đây có gì thú vị?”",
      helpExampleThree: "Chọn số của một địa điểm để đặt làm chủ đề cho câu hỏi tiếp theo.",
      locationRequesting: "Đang chờ quyền truy cập từ trình duyệt…",
      locationReady: "Đã sẵn sàng sử dụng vị trí. Câu trả lời gần bạn sẽ phù hợp hơn.",
      locationDenied: "Bạn chưa cấp quyền vị trí. Bạn vẫn có thể trò chuyện hoặc thử lại.",
      locationUnavailable: "Trình duyệt này không cung cấp được vị trí.",
      locationError: "Không thể chuẩn bị vị trí. Vui lòng thử lại.",
      locationReadyBadge: "Đã bật vị trí",
      chatPlaceholder: "Bạn muốn tìm gì?",
      emptyQuestion: "Vui lòng nhập câu hỏi hoặc số của địa điểm.",
      networkError: "Không thể gửi tin nhắn. Vui lòng thử lại.",
      assistantLoadError: "Không thể tải LEO. Vui lòng tải lại trang và thử lại."
    },
    en: {
      help: "Help",
      exploreWithContext: "Explore with context",
      heroTitle: "Explore Places with LEO",
      heroDescription: "Ask about nearby places, get local ideas, or continue a conversation about a place you selected.",
      heroDescriptionMobile: "Discover nearby places with a little help from LEO.",
      locationHelps: "Location helps LEO be useful",
      locationPrivacy: "Your browser asks for permission. We use your location to find nearby places, not to track you.",
      chatWithLeo: "Chat with LEO",
      online: "Online",
      chatHint: "Try “coffee near me” or choose a suggestion.",
      locationOff: "Location off",
      preparingAssistant: "Preparing your local assistant…",
      yourContext: "Your context",
      currentLocation: "Current location",
      checkingLocation: "Checking whether location is available…",
      coordinates: "Coordinates",
      notAvailable: "Not available",
      accuracy: "Accuracy",
      available: "Available",
      language: "Language",
      useMyLocation: "Use my location",
      refreshLocation: "Refresh location",
      gettingLocation: "Getting location…",
      permissionHint: "You can change this permission in your browser settings.",
      startExploring: "Start exploring",
      whatLookingFor: "What are you looking for?",
      loadingRecommendations: "Loading nearby suggestions…",
      locationSuggestionsUnavailable: "Allow location access to load nearby suggestions.",
      nearbyHint: "LEO will use your location when a nearby search needs it.",
      madeBy: "Made by",
      privateByDesign: "· Private by design",
      locationOptional: "Location services are optional.",
      helpTitle: "Get more from LEO",
      helpDescription: "Ask naturally. For local discovery, include “near me” and allow location access when prompted.",
      helpExampleOne: "“Find the nearest church”",
      helpExampleTwo: "“What can I do around here?”",
      helpExampleThree: "Choose a place number to make it the focus of your next questions.",
      locationRequesting: "Waiting for browser permission…",
      locationReady: "Location ready. Nearby answers will be more relevant.",
      locationDenied: "Location access was not granted. You can still chat, or try again.",
      locationUnavailable: "Location is unavailable in this browser.",
      locationError: "We could not prepare location. Please try again.",
      locationReadyBadge: "Location ready",
      chatPlaceholder: "What would you like to find?",
      emptyQuestion: "Please enter a question or a place number.",
      networkError: "Unable to send your message. Please try again.",
      assistantLoadError: "LEO could not load. Please refresh the page and try again."
    }
  };

  window.leoUiText = function (key) {
    var language = window.LEO_UI_LANGUAGE === "en" ? "en" : "vi";
    return (window.LEO_UI_TEXTS[language] && window.LEO_UI_TEXTS[language][key])
      || window.LEO_UI_TEXTS.vi[key]
      || key;
  };

  var latestLocationDetail = { state: "pending" };
  var recommendedActions = null;

  function renderRecommendedActions(actions) {
    recommendedActions = Array.isArray(actions) ? actions : null;
    var $container = $("#leobot_quick_actions").empty();
    if (recommendedActions === null || recommendedActions.length === 0) {
      var messageKey = recommendedActions === null
        ? "loadingRecommendations"
        : "locationSuggestionsUnavailable";
      $("<p>", { class: "small text-secondary mb-0" })
        .text(window.leoUiText(messageKey))
        .appendTo($container);
      return;
    }

    recommendedActions.forEach(function (action) {
      if (!action || !action.label || !action.question) return;
      var label = action.label[window.LEO_UI_LANGUAGE];
      var question = action.question[window.LEO_UI_LANGUAGE];
      if (typeof label !== "string" || typeof question !== "string") return;

      var icon = typeof action.icon === "string" &&
        /^fa-[a-z0-9-]+$/.test(action.icon)
        ? action.icon
        : "fa-compass";
      var $button = $("<button>", {
        type: "button",
        class: "btn btn-light text-start rounded-3 leobot-quick-action"
      }).attr("data-question", question);
      $("<i>", {
        class: "fa " + icon + " text-primary me-2",
        "aria-hidden": "true"
      }).appendTo($button);
      $("<span>").text(label).appendTo($button);
      $button.appendTo($container);
    });

    if (!$container.find(".leobot-quick-action").length) {
      $("<p>", { class: "small text-secondary mb-0" })
        .text(window.leoUiText("locationSuggestionsUnavailable"))
        .appendTo($container);
    }
  }

  function applyLanguage(language) {
    window.LEO_UI_LANGUAGE = language === "en" ? "en" : "vi";
    try {
      window.localStorage.setItem("leobot_ui_language", window.LEO_UI_LANGUAGE);
    } catch (error) {
      console.warn("Unable to save LEO language preference.", error);
    }

    $("html").attr("lang", window.LEO_UI_LANGUAGE);
    $("#leobot_language").val(window.LEO_UI_LANGUAGE);
    $("#leobot_language").attr("aria-label", window.leoUiText("language"));
    $("#leobot_help_button")
      .attr("aria-label", window.leoUiText("help"))
      .attr("title", window.leoUiText("help"));
    $("[data-i18n]").each(function () {
      $(this).text(window.leoUiText($(this).data("i18n")));
    });
    renderRecommendedActions(recommendedActions);
    $("#LEO_ChatBot_Container .botui-actions-text-input")
      .attr("placeholder", window.leoUiText("chatPlaceholder"));

    var $greeting = $("#LEO_ChatBot_Container .leobot-answer .botui-message-content").first();
    if ($greeting.length && typeof getGreetingMessage === "function") {
      $greeting.text(getGreetingMessage(
        window.currentUserProfile ? window.currentUserProfile.displayName : "",
        window.LEO_UI_LANGUAGE
      ));
    }
    updateLocationPanel(latestLocationDetail);
  }

  function updateLocationPanel(detail) {
    latestLocationDetail = detail || { state: "pending" };
    var $status = $("#leobot_location_status");
    var $button = $("#leobot_location_button");
    var $icon = $("#leobot_location_icon");
    var $badge = $("#leobot_chat_location_badge");
    var $coordinates = $("#leobot_location_coordinates");
    var $accuracy = $("#leobot_location_accuracy");
    if (!$status.length || !$button.length || !$icon.length) return;

    var state = latestLocationDetail.state || "pending";
    var messages = {
      pending: ["secondary", "fa-circle-o-notch fa-spin", "checkingLocation"],
      requesting: ["info", "fa-location-arrow", "locationRequesting"],
      ready: ["success", "fa-check-circle", "locationReady"],
      denied: ["warning", "fa-info-circle", "locationDenied"],
      unavailable: ["warning", "fa-exclamation-triangle", "locationUnavailable"],
      error: ["danger", "fa-exclamation-circle", "locationError"]
    };
    var message = messages[state] || messages.error;
    $status.attr("class", "alert alert-" + message[0] + " small mb-3")
      .empty()
      .append($("<i>", {
        class: "fa " + message[1] + " me-2",
        "aria-hidden": "true"
      }))
      .append($("<span>").text(window.leoUiText(message[2])));

    $icon.attr("class", "leobot-location-icon is-" + state);
    $button.prop("disabled", state === "requesting").empty();
    if (state === "requesting") {
      $("<span>", {
        class: "spinner-border spinner-border-sm me-2",
        "aria-hidden": "true"
      }).appendTo($button);
      $button.append(document.createTextNode(window.leoUiText("gettingLocation")));
    } else {
      $("<i>", {
        class: "fa fa-crosshairs me-2",
        "aria-hidden": "true"
      }).appendTo($button);
      $button.append(document.createTextNode(
        window.leoUiText(state === "ready" ? "refreshLocation" : "useMyLocation")
      ));
    }

    if (state === "ready" && latestLocationDetail.data) {
      var data = latestLocationDetail.data;
      var latitude = Number(data.latitude);
      var longitude = Number(data.longitude);
      if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
        $coordinates.text(latitude.toFixed(5) + ", " + longitude.toFixed(5));
      }
      $accuracy.text(data.accuracy
        ? "±" + Math.round(data.accuracy) + " m"
        : window.leoUiText("available"));
      renderRecommendedActions(
        Array.isArray(data.recommended_actions) ? data.recommended_actions : []
      );
      $badge.attr(
        "class",
        "badge rounded-pill text-bg-success-subtle text-success-emphasis d-none d-sm-inline-flex align-items-center gap-1"
      ).empty()
        .append($("<i>", { class: "fa fa-location-arrow", "aria-hidden": "true" }))
        .append(document.createTextNode(window.leoUiText("locationReadyBadge")));
    } else if (state !== "ready") {
      if (["denied", "unavailable", "error"].indexOf(state) !== -1) {
        renderRecommendedActions([]);
      }
      $badge.attr(
        "class",
        "badge rounded-pill text-bg-light text-secondary d-none d-sm-inline-flex align-items-center gap-1"
      ).empty()
        .append($("<i>", { class: "fa fa-location-arrow", "aria-hidden": "true" }))
        .append(document.createTextNode(window.leoUiText("locationOff")));
    }
  }

  function scrollToChatOnMobile() {
    var isMobile =
      typeof window.matchMedia === "function"
        ? window.matchMedia("(max-width: 991.98px)").matches
        : window.innerWidth <= 991;
    if (!isMobile) return;

    var chat = document.getElementById("LEO_ChatBot_Container");
    if (!chat || chat.getClientRects().length === 0) {
      chat = document.getElementById("leobot_chat_container");
    }
    if (!chat) return;

    var prefersReducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    chat.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start",
    });
  }

  function startChatbot() {
    var $loader = $("#LEO_ChatBot_Container_Loader");
    var $chat = $("#LEO_ChatBot_Container");
    var startupComplete = false;

    function startChat(visitorId) {
      if (startupComplete) return;
      startupComplete = true;
      window.clearTimeout(startupFallback);
      if (typeof window.startLeoChatBot === "function") {
        window.startLeoChatBot(visitorId);
        return;
      }

      $loader.removeClass("d-flex").addClass("d-none").hide();
      var $error = $("<div>", {
        class: "alert alert-danger m-3",
        role: "alert"
      }).append(
        $("<i>", {
          class: "fa fa-exclamation-circle me-2",
          "aria-hidden": "true"
        }),
        document.createTextNode(window.leoUiText("assistantLoadError"))
      );
      $chat.stop(true, true).show().css("opacity", "1").empty().append($error);
    }

    var startupFallback = window.setTimeout(function () {
      startChat();
    }, 8000);
    var observerScript = window.location.protocol + "//" + HOSTNAME
      + "/resources/js/leocdp.observer.js";
    var allowedHost = ["leobot.leocdp.com", "leobot.example.com"]
      .indexOf(window.location.hostname) !== -1;

    if (CDP_TRACKING && allowedHost) {
      $.getScript(observerScript)
        .done(function () {
          startChat();
        })
        .fail(function () {
          console.warn("LEO observer failed to load; starting chatbot without tracking.");
          startChat();
        });
    } else {
      startChat();
    }
  }

  $(function () {
    $(document).on("leo:location", function (event, detail) {
      updateLocationPanel(detail || {});
    });
    $("#leobot_location_button").on("click", function () {
      if (
        typeof window.requestUserGeolocation === "function"
        && window.currentUserProfile
      ) {
        window.requestUserGeolocation(window.currentUserProfile.visitorId, true);
      }
    });
    $("#leobot_language").on("change", function () {
      applyLanguage($(this).val());
    });
    $("#leobot_quick_actions").on("click", ".leobot-quick-action", function () {
      scrollToChatOnMobile();
      var question = $(this).attr("data-question");
      if (question && typeof window.sendQuestionToLeoAI === "function") {
        window.sendQuestionToLeoAI("ask", question);
        window.getBotUI().message.human({ content: question });
      }
    });

    applyLanguage(window.LEO_UI_LANGUAGE);
    startChatbot();
  });
})(jQuery, window, document);