CREATE TYPE "public"."iot_approval" AS ENUM('approved', 'unapproved', 'quarantined');--> statement-breakpoint
ALTER TABLE "iot_devices" ADD COLUMN "firewall_zone" text;--> statement-breakpoint
ALTER TABLE "iot_devices" ADD COLUMN "nac_policy" text;--> statement-breakpoint
ALTER TABLE "iot_devices" ADD COLUMN "owner" text;--> statement-breakpoint
ALTER TABLE "iot_devices" ADD COLUMN "approval" "iot_approval" DEFAULT 'unapproved' NOT NULL;