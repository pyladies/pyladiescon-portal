from django.urls import path

from . import views

app_name = "speakers"

urlpatterns = [
    path("", views.SpeakerPortalIndexView.as_view(), name="index"),
    path(
        "invitations/<str:token>/",
        views.InvitationView.as_view(),
        name="invitation",
    ),
    path("sessions/", views.SessionListView.as_view(), name="session_list"),
    path("sessions/new/", views.SessionCreateView.as_view(), name="session_create"),
    path(
        "sessions/new-program-item/",
        views.ProgramItemCreateView.as_view(),
        name="program_item_create",
    ),
    path(
        "sessions/<int:pk>/",
        views.SessionDetailView.as_view(),
        name="session_detail",
    ),
    path(
        "sessions/<int:pk>/edit/",
        views.SessionUpdateView.as_view(),
        name="session_edit",
    ),
    path(
        "sessions/<int:pk>/presenters/add/",
        views.SessionAddPresenterView.as_view(),
        name="session_add_presenter",
    ),
    path(
        "sessions/<int:pk>/presenters/<int:link_pk>/remove/",
        views.SessionRemovePresenterView.as_view(),
        name="session_remove_presenter",
    ),
    path(
        "sessions/<int:pk>/presenters/<int:link_pk>/invite/",
        views.SessionInviteView.as_view(),
        name="session_invite",
    ),
    path("presenters/", views.PresenterListView.as_view(), name="presenter_list"),
    path(
        "presenters/new/",
        views.PresenterCreateView.as_view(),
        name="presenter_create",
    ),
    path(
        "presenters/<int:pk>/",
        views.PresenterDetailView.as_view(),
        name="presenter_detail",
    ),
    path(
        "presenters/<int:pk>/edit/",
        views.PresenterUpdateView.as_view(),
        name="presenter_edit",
    ),
    path("settings/types/", views.ProgramTypesView.as_view(), name="program_types"),
    path(
        "settings/types/new/",
        views.SessionTypeCreateView.as_view(),
        name="session_type_create",
    ),
    path(
        "settings/types/<int:pk>/",
        views.SessionTypeUpdateView.as_view(),
        name="session_type_edit",
    ),
    path(
        "settings/roles/new/",
        views.PresenterRoleCreateView.as_view(),
        name="presenter_role_create",
    ),
    path(
        "settings/roles/<int:pk>/",
        views.PresenterRoleUpdateView.as_view(),
        name="presenter_role_edit",
    ),
    path("me/", views.SpeakerDashboardView.as_view(), name="my_dashboard"),
    path("me/profile/", views.SpeakerProfileUpdateView.as_view(), name="my_profile"),
    path("me/sessions/", views.SpeakerSessionListView.as_view(), name="my_sessions"),
    path(
        "me/sessions/<int:pk>/edit/",
        views.SpeakerSessionUpdateView.as_view(),
        name="my_session_edit",
    ),
    path(
        "me/sessions/<int:pk>/suggest/",
        views.SuggestCoPresenterView.as_view(),
        name="my_session_suggest",
    ),
    path("me/schedule/", views.SpeakerScheduleView.as_view(), name="my_schedule"),
    path(
        "me/items/<int:pk>/toggle/",
        views.SpeakerItemToggleView.as_view(),
        name="my_item_toggle",
    ),
    path("checklists/", views.ChecklistBoardView.as_view(), name="checklist_board"),
    path(
        "checklists/export/",
        views.ChecklistBoardExportView.as_view(),
        name="checklist_board_export",
    ),
    path(
        "checklists/queue/", views.ChecklistQueueView.as_view(), name="checklist_queue"
    ),
    path("items/<int:pk>/status/", views.ItemStatusView.as_view(), name="item_status"),
    path("items/<int:pk>/assign/", views.ItemAssignView.as_view(), name="item_assign"),
    path(
        "presenters/<int:pk>/items/add/",
        views.PresenterAddItemView.as_view(),
        name="presenter_add_item",
    ),
    path(
        "invitations/<int:pk>/resend/",
        views.InvitationResendView.as_view(),
        name="invitation_resend",
    ),
    path(
        "invitations/<int:pk>/cancel/",
        views.InvitationCancelView.as_view(),
        name="invitation_cancel",
    ),
]
