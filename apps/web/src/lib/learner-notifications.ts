export type LearnerNotification = {
  id: string;
  assignmentId: string;
  taskTitle: string;
  decision: "PASS" | "REVISION_REQUIRED";
  reviewedAt: string;
  readAt: string | null;
};

export type LearnerNotificationPage = {
  items: LearnerNotification[];
  unreadCount: number;
  nextCursor: string | null;
};
