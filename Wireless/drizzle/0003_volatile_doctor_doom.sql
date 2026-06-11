ALTER TYPE "public"."incident_status" ADD VALUE 'vendor_escalated';--> statement-breakpoint
CREATE TABLE "incident_notes" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"incident_id" uuid NOT NULL,
	"author" text DEFAULT 'ops' NOT NULL,
	"body" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "incidents" ADD COLUMN "alert_id" uuid;--> statement-breakpoint
ALTER TABLE "incidents" ADD COLUMN "category" text;--> statement-breakpoint
ALTER TABLE "incidents" ADD COLUMN "owner" text;--> statement-breakpoint
ALTER TABLE "incidents" ADD COLUMN "sla_due_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "incident_notes" ADD CONSTRAINT "incident_notes_incident_id_incidents_id_fk" FOREIGN KEY ("incident_id") REFERENCES "public"."incidents"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "incident_notes_incident_idx" ON "incident_notes" USING btree ("incident_id");--> statement-breakpoint
ALTER TABLE "incidents" ADD CONSTRAINT "incidents_alert_id_alerts_id_fk" FOREIGN KEY ("alert_id") REFERENCES "public"."alerts"("id") ON DELETE set null ON UPDATE no action;